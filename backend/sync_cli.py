import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.sync import sync_connection
from app.database import SessionLocal
from app.models import BankConnection, ConnectionStatus
from app.providers.enable_banking import get_bank_provider


def main() -> None:
    db = SessionLocal()
    provider = get_bank_provider()
    connections = db.query(BankConnection).filter(BankConnection.status == ConnectionStatus.active.value).all()
    for connection in connections:
        imported = sync_connection(db, connection, provider)
        print(f"connection={connection.id} institution={connection.institution_name} imported={imported}")
    db.close()


if __name__ == "__main__":
    main()
