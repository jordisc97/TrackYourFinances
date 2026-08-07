from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import Account, AccountSource, BalanceSnapshot, BankConnection, ConnectionStatus, Transaction, TransactionSource
from app.providers.base import BankProvider
from app.services.classification import classify_transaction


def upsert_balance(db: Session, account: Account, amount: float, snapshot_date: date | None = None) -> None:
    snapshot_date = snapshot_date or date.today()
    existing = db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == account.id, BalanceSnapshot.snapshot_date == snapshot_date).first()
    if existing:
        existing.amount = amount
        return
    db.add(BalanceSnapshot(account_id=account.id, snapshot_date=snapshot_date, amount=amount))


def sync_connection(db: Session, connection: BankConnection, provider: BankProvider) -> int:
    if not connection.session_id:
        connection.status = ConnectionStatus.error.value
        db.commit()
        return 0
    accounts = provider.fetch_accounts(connection.session_id)
    imported = 0
    synced_accounts: list[Account] = []
    for pa in accounts:
        account = (
            db.query(Account)
            .filter(Account.household_id == connection.household_id, Account.external_id == pa.external_id)
            .first()
        )
        if account is None:
            account = Account(
                household_id=connection.household_id,
                bank_connection_id=connection.id,
                name=f"{connection.institution_name} {pa.name}",
                institution=connection.institution_name,
                currency=pa.currency,
                account_type=pa.account_type,
                source=AccountSource.bank.value,
                external_id=pa.external_id,
                iban=pa.iban,
            )
            db.add(account)
            db.flush()
        else:
            account.bank_connection_id = connection.id
            account.iban = pa.iban or account.iban
            account.name = f"{connection.institution_name} {pa.name}"
        upsert_balance(db, account, pa.balance)
        synced_accounts.append(account)
    connection.last_synced_at = datetime.utcnow()
    connection.status = ConnectionStatus.active.value
    if connection.consent_expires_at and connection.consent_expires_at < datetime.utcnow():
        connection.status = ConnectionStatus.expired.value
    db.commit()
    for account in synced_accounts:
        if not account.external_id:
            continue
        for pt in provider.fetch_transactions(connection.session_id, account.external_id):
            exists = db.query(Transaction).filter(Transaction.account_id == account.id, Transaction.external_id == pt.external_id).first()
            if exists:
                exists.amount = pt.amount
                exists.raw_description = pt.description or exists.raw_description
                exists.merchant = pt.merchant or exists.merchant
                exists.counterparty = pt.counterparty or exists.counterparty
                exists.counterparty_iban = pt.counterparty_iban or exists.counterparty_iban
                exists.location = pt.location or exists.location
                exists.mcc = pt.mcc or exists.mcc
                exists.value_date = pt.value_date or exists.value_date
                exists.balance_after = pt.balance_after if pt.balance_after is not None else exists.balance_after
                continue
            tx = Transaction(
                account_id=account.id,
                booked_at=pt.booked_at,
                amount=pt.amount,
                currency=pt.currency,
                raw_description=pt.description,
                merchant=pt.merchant or "",
                counterparty=pt.counterparty or "",
                counterparty_iban=pt.counterparty_iban or "",
                location=pt.location or "",
                mcc=pt.mcc,
                value_date=pt.value_date,
                balance_after=pt.balance_after,
                external_id=pt.external_id,
                source=TransactionSource.bank.value,
            )
            classify_transaction(db, connection.household_id, tx, use_llm=False)
            db.add(tx)
            imported += 1
    connection.last_synced_at = datetime.utcnow()
    db.commit()
    return imported
