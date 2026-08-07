from collections import defaultdict

from sqlalchemy.orm import Session, joinedload

from app.models import Account, Category, Transaction
from app.schemas import AccountFlowOut, FlowEdgeOut, FlowNodeOut
from app.services.accounts_helpers import (
    EDGE_KIND_INCOME,
    EDGE_KIND_SPEND,
    EDGE_KIND_TRANSFER,
    EXPENSES_NODE_ID,
    INCOME_NODE_ID,
    NODE_KIND_ACCOUNT,
    NODE_KIND_EXPENSES,
    NODE_KIND_INCOME,
    account_node_id,
    match_own_account_id,
    normalize_iban,
)
from app.services.classification import TRANSFER_CATEGORY_NAME
from app.services.dashboard import is_spend_outflow, is_wage_inflow, month_transactions, spend_amount

TRANSFER_KIND = "transfer"


def _account_label(account: Account) -> str:
    return account.name


def build_account_flow(db: Session, household_id: int, year: int, month: int) -> AccountFlowOut:
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).order_by(Account.name.asc()).all()
    txs = month_transactions(db, household_id, year, month)
    income_by_account: dict[int, float] = defaultdict(float)
    spend_by_account: dict[int, float] = defaultdict(float)
    transfer_pairs: dict[tuple[int, int], float] = defaultdict(float)
    for tx in txs:
        if is_wage_inflow(tx):
            income_by_account[tx.account_id] += tx.amount
            continue
        if is_spend_outflow(tx):
            spend_by_account[tx.account_id] += abs(spend_amount(tx))
            continue
        kind = tx.category.kind if tx.category is not None else None
        if tx.amount >= 0 or kind != TRANSFER_KIND:
            continue
        target_id = match_own_account_id(accounts, tx.raw_description, tx.merchant, exclude_account_id=tx.account_id)
        if target_id is None:
            continue
        transfer_pairs[(tx.account_id, target_id)] += abs(tx.amount)
    total_income = round(sum(income_by_account.values()), 2)
    total_spend = round(sum(spend_by_account.values()), 2)
    nodes = [
        FlowNodeOut(id=INCOME_NODE_ID, kind=NODE_KIND_INCOME, label="Income", amount=total_income),
        *[
            FlowNodeOut(
                id=account_node_id(a.id),
                kind=NODE_KIND_ACCOUNT,
                label=_account_label(a),
                amount=round(income_by_account.get(a.id, 0.0) - spend_by_account.get(a.id, 0.0), 2),
                account_id=a.id,
                iban=normalize_iban(a.iban),
            )
            for a in accounts
        ],
        FlowNodeOut(id=EXPENSES_NODE_ID, kind=NODE_KIND_EXPENSES, label="Expenses", amount=total_spend),
    ]
    edges: list[FlowEdgeOut] = []
    for account_id, amount in income_by_account.items():
        if amount <= 0:
            continue
        edges.append(FlowEdgeOut(source=INCOME_NODE_ID, target=account_node_id(account_id), amount=round(amount, 2), kind=EDGE_KIND_INCOME))
    for account_id, amount in spend_by_account.items():
        if amount <= 0:
            continue
        edges.append(FlowEdgeOut(source=account_node_id(account_id), target=EXPENSES_NODE_ID, amount=round(amount, 2), kind=EDGE_KIND_SPEND))
    for (source_id, target_id), amount in transfer_pairs.items():
        if amount <= 0:
            continue
        edges.append(FlowEdgeOut(source=account_node_id(source_id), target=account_node_id(target_id), amount=round(amount, 2), kind=EDGE_KIND_TRANSFER))
    return AccountFlowOut(year=year, month=month, nodes=nodes, edges=edges)


def reclassify_own_account_transfers(db: Session, household_id: int) -> int:
    transfer = db.query(Category).filter(Category.household_id == household_id, Category.name == TRANSFER_CATEGORY_NAME).first()
    if transfer is None:
        return 0
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).all()
    account_ids = [a.id for a in accounts]
    if not account_ids:
        return 0
    txs = db.query(Transaction).options(joinedload(Transaction.category)).filter(Transaction.account_id.in_(account_ids)).all()
    updated = 0
    for tx in txs:
        if match_own_account_id(accounts, tx.raw_description, tx.merchant, exclude_account_id=tx.account_id) is None:
            continue
        if tx.category_id == transfer.id:
            continue
        tx.category_id = transfer.id
        updated += 1
    if updated:
        db.commit()
    return updated
