from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot, Transaction, TransactionSplit


def purge_account_data(db: Session, account: Account) -> None:
    tx_ids = [row[0] for row in db.query(Transaction.id).filter(Transaction.account_id == account.id).all()]
    if tx_ids:
        db.query(TransactionSplit).filter(TransactionSplit.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
        db.query(Transaction).filter(Transaction.id.in_(tx_ids)).delete(synchronize_session=False)
    db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == account.id).delete(synchronize_session=False)
    db.delete(account)


def purge_inactive_accounts(db: Session, household_id: int) -> int:
    inactive = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(False)).all()
    for account in inactive:
        purge_account_data(db, account)
    return len(inactive)
