from collections import defaultdict

from sqlalchemy.orm import Session, joinedload

from app.models import Account, AccountType, Category, Transaction
from app.schemas import AccountFlowOut, FlowEdgeOut, FlowNodeOut
from app.services.accounts_helpers import (
    EDGE_KIND_INCOME,
    EDGE_KIND_INVEST,
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
INVESTMENT_KIND = "investment"
ACTIVITY_CASH_TOP_UP = "cash_top_up"
FUNDING_ACCOUNT_TYPES = (AccountType.checking.value, AccountType.savings.value)


def _account_label(account: Account) -> str:
    return account.name


def _default_funding_account_id(accounts: list[Account], income_by_account: dict[int, float], exclude_account_id: int) -> int | None:
    candidates = [a for a in accounts if a.account_type in FUNDING_ACCOUNT_TYPES and a.id != exclude_account_id]
    if not candidates:
        return None
    return max(candidates, key=lambda a: (income_by_account.get(a.id, 0.0), a.id)).id


def _first_investment_account_id(accounts: list[Account], exclude_account_id: int) -> int | None:
    for account in accounts:
        if account.id != exclude_account_id and account.account_type == AccountType.investment.value:
            return account.id
    return None


def build_account_flow(db: Session, household_id: int, year: int, month: int) -> AccountFlowOut:
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).order_by(Account.name.asc()).all()
    accounts_by_id = {a.id: a for a in accounts}
    txs = month_transactions(db, household_id, year, month)
    income_by_account: dict[int, float] = defaultdict(float)
    spend_by_account: dict[int, float] = defaultdict(float)
    transfer_pairs: dict[tuple[int, int], float] = defaultdict(float)
    invest_from_income: dict[int, float] = defaultdict(float)
    income_diverted_from: dict[int, float] = defaultdict(float)
    cash_top_ups: list[Transaction] = []
    investment_outflows: list[Transaction] = []
    transfer_outflows: list[Transaction] = []
    for tx in txs:
        if is_wage_inflow(tx):
            income_by_account[tx.account_id] += tx.amount
            continue
        if is_spend_outflow(tx):
            spend_by_account[tx.account_id] += abs(spend_amount(tx))
            continue
        kind = tx.category.kind if tx.category is not None else None
        if tx.investment_activity == ACTIVITY_CASH_TOP_UP and tx.amount > 0:
            cash_top_ups.append(tx)
            continue
        if tx.amount < 0 and kind == TRANSFER_KIND:
            transfer_outflows.append(tx)
            continue
        if tx.amount < 0 and kind == INVESTMENT_KIND:
            investment_outflows.append(tx)
    top_up_account_ids = {tx.account_id for tx in cash_top_ups}
    for tx in cash_top_ups:
        funding_id = match_own_account_id(accounts, tx.raw_description, tx.merchant, exclude_account_id=tx.account_id)
        if funding_id is None:
            funding_id = _default_funding_account_id(accounts, income_by_account, tx.account_id)
        amount = abs(tx.amount)
        invest_from_income[tx.account_id] += amount
        if funding_id is not None:
            income_diverted_from[funding_id] += amount
    for tx in transfer_outflows:
        target_id = match_own_account_id(accounts, tx.raw_description, tx.merchant, exclude_account_id=tx.account_id)
        if target_id is None:
            continue
        target = accounts_by_id.get(target_id)
        amount = abs(tx.amount)
        if target is not None and target.account_type == AccountType.investment.value:
            if target_id in top_up_account_ids:
                continue
            invest_from_income[target_id] += amount
            income_diverted_from[tx.account_id] += amount
            continue
        transfer_pairs[(tx.account_id, target_id)] += amount
    for tx in investment_outflows:
        target_id = match_own_account_id(accounts, tx.raw_description, tx.merchant, exclude_account_id=tx.account_id)
        if target_id is None:
            target_id = _first_investment_account_id(accounts, tx.account_id)
        if target_id is None or target_id in top_up_account_ids:
            continue
        amount = abs(tx.amount)
        invest_from_income[target_id] += amount
        income_diverted_from[tx.account_id] += amount
    total_income = round(sum(income_by_account.values()), 2)
    total_spend = round(sum(spend_by_account.values()), 2)
    nodes = [
        FlowNodeOut(id=INCOME_NODE_ID, kind=NODE_KIND_INCOME, label="Income", amount=total_income),
        *[
            FlowNodeOut(
                id=account_node_id(a.id),
                kind=NODE_KIND_ACCOUNT,
                label=_account_label(a),
                amount=_account_node_amount(a, income_by_account, spend_by_account, invest_from_income, income_diverted_from),
                account_id=a.id,
                iban=normalize_iban(a.iban),
            )
            for a in accounts
        ],
        FlowNodeOut(id=EXPENSES_NODE_ID, kind=NODE_KIND_EXPENSES, label="Expenses", amount=total_spend),
    ]
    edges: list[FlowEdgeOut] = []
    for account_id, amount in income_by_account.items():
        to_account = round(amount - income_diverted_from.get(account_id, 0.0), 2)
        if to_account <= 0:
            continue
        edges.append(FlowEdgeOut(source=INCOME_NODE_ID, target=account_node_id(account_id), amount=to_account, kind=EDGE_KIND_INCOME))
    for target_id, amount in invest_from_income.items():
        if amount <= 0:
            continue
        edges.append(FlowEdgeOut(source=INCOME_NODE_ID, target=account_node_id(target_id), amount=round(amount, 2), kind=EDGE_KIND_INVEST))
    for account_id, amount in spend_by_account.items():
        if amount <= 0:
            continue
        edges.append(FlowEdgeOut(source=account_node_id(account_id), target=EXPENSES_NODE_ID, amount=round(amount, 2), kind=EDGE_KIND_SPEND))
    for (source_id, target_id), amount in transfer_pairs.items():
        if amount <= 0:
            continue
        edges.append(FlowEdgeOut(source=account_node_id(source_id), target=account_node_id(target_id), amount=round(amount, 2), kind=EDGE_KIND_TRANSFER))
    return AccountFlowOut(year=year, month=month, nodes=nodes, edges=edges)


def _account_node_amount(
    account: Account,
    income_by_account: dict[int, float],
    spend_by_account: dict[int, float],
    invest_from_income: dict[int, float],
    income_diverted_from: dict[int, float],
) -> float:
    if account.account_type == AccountType.investment.value:
        return round(invest_from_income.get(account.id, 0.0), 2)
    return round(
        income_by_account.get(account.id, 0.0)
        - income_diverted_from.get(account.id, 0.0)
        - spend_by_account.get(account.id, 0.0),
        2,
    )


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
