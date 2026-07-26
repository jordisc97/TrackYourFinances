from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.config import get_settings
from app.database import Base, engine
from app.routers import accounts, auth, banking, dashboard, import_csv, transactions
from app.services.category_migration import migrate_all_household_categories


def _purge_stored_client_tokens() -> None:
    # Never persist bank OAuth token payloads; clear any legacy ciphertext.
    with engine.begin() as connection:
        tables = inspect(connection).get_table_names()
        if "bank_connections" not in tables:
            return
        columns = {column["name"] for column in inspect(connection).get_columns("bank_connections")}
        if "encrypted_tokens" not in columns:
            return
        connection.execute(text("UPDATE bank_connections SET encrypted_tokens = NULL WHERE encrypted_tokens IS NOT NULL"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    _purge_stored_client_tokens()
    migrate_all_household_categories()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(import_csv.router)
app.include_router(banking.router)
app.include_router(dashboard.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
