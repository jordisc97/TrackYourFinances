from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.config import get_settings
from app.database import Base, SessionLocal, configure_sqlite_wal, engine
from app.routers import accounts, advisor, auth, banking, dashboard, import_csv, transactions
from app.seed import ensure_all_household_defaults
from app.services.classification import backfill_known_commerces


def ensure_schema() -> None:
    configure_sqlite_wal()
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "households" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("households")}
        if "location" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE households ADD COLUMN location VARCHAR(120) DEFAULT ''"))
    if "monthly_strategies" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("monthly_strategies")}
        if "invest_pct" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE monthly_strategies ADD COLUMN invest_pct FLOAT DEFAULT 25.0"))
                if "crypto_pct" in cols:
                    conn.execute(text("UPDATE monthly_strategies SET invest_pct = COALESCE(crypto_pct, 0) + COALESCE(stocks_pct, 0) + COALESCE(etfs_pct, 0)"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    ensure_all_household_defaults()
    db = SessionLocal()
    backfill_known_commerces(db)
    db.close()
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
app.include_router(advisor.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
