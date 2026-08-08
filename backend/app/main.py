from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import inspect, text

from app.config import get_settings
from app.database import Base, SessionLocal, configure_sqlite_wal, engine
from app.routers import accounts, advisor, auth, banking, dashboard, import_csv, transactions
from app.seed import ensure_all_household_defaults
from app.services.classification import backfill_known_commerces
from app.services.periodic_categorize import categorize_all_households

logger = logging.getLogger(__name__)

PRIVACY_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Privacy — TrackYourFinances</title>
<style>body{font-family:system-ui,sans-serif;max-width:42rem;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#111}
h1{font-size:1.6rem}h2{font-size:1.1rem;margin-top:1.5rem}.muted{color:#666}</style></head><body>
<h1>Privacy policy</h1><p class="muted">Last updated: 3 August 2026</p>
<h2>Who we are</h2><p>TrackYourFinances is a private household finance tracker. It helps you sync and review balances and transactions for personal use.</p>
<h2>What we collect</h2><p>With your consent, we retrieve account balances and transaction history from your bank through Enable Banking. We also store account details you enter manually and CSV imports.</p>
<h2>How data is stored</h2><p>Bank and household data is stored locally in your TrackYourFinances instance. It is not sold, rented, or shared with advertisers.</p>
<h2>Bank access</h2><p>Bank connections use Open Banking consent via Enable Banking. You can revoke access anytime through your bank or by disconnecting in TrackYourFinances.</p>
<h2>Contact</h2><p>For data-protection questions, use the email registered with the Enable Banking application that provides the bank connection.</p>
</body></html>"""

TERMS_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Terms — TrackYourFinances</title>
<style>body{font-family:system-ui,sans-serif;max-width:42rem;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#111}
h1{font-size:1.6rem}h2{font-size:1.1rem;margin-top:1.5rem}.muted{color:#666}</style></head><body>
<h1>Terms of service</h1><p class="muted">Last updated: 3 August 2026</p>
<h2>Personal use</h2><p>TrackYourFinances is for personal, non-commercial household use. You may only connect bank accounts you are authorized to access.</p>
<h2>Bank consent</h2><p>Connecting a bank means you authorize Enable Banking and TrackYourFinances to retrieve account information according to the consent you grant. Consent can be revoked at the bank anytime.</p>
<h2>Accuracy</h2><p>Balances and transactions depend on your bank and Open Banking providers. The app does not provide financial, tax, or investment advice.</p>
<h2>Availability</h2><p>The service may be interrupted for maintenance, provider outages, or expired bank consent.</p>
</body></html>"""


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
        legacy_asset_cols = ("crypto_pct", "stocks_pct", "etfs_pct")
        if "invest_pct" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE monthly_strategies ADD COLUMN invest_pct FLOAT DEFAULT 25.0"))
                if "crypto_pct" in cols:
                    conn.execute(text("UPDATE monthly_strategies SET invest_pct = COALESCE(crypto_pct, 0) + COALESCE(stocks_pct, 0) + COALESCE(etfs_pct, 0)"))
        cols = {c["name"] for c in inspect(engine).get_columns("monthly_strategies")}
        drop_cols = [name for name in legacy_asset_cols if name in cols]
        if drop_cols:
            with engine.begin() as conn:
                if "crypto_pct" in cols:
                    conn.execute(text("UPDATE monthly_strategies SET invest_pct = COALESCE(invest_pct, COALESCE(crypto_pct, 0) + COALESCE(stocks_pct, 0) + COALESCE(etfs_pct, 0))"))
                for name in drop_cols:
                    conn.execute(text(f"ALTER TABLE monthly_strategies DROP COLUMN {name}"))
    if "transactions" in inspector.get_table_names():
        tx_cols = {c["name"] for c in inspector.get_columns("transactions")}
        additions = [
            ("counterparty", "ALTER TABLE transactions ADD COLUMN counterparty VARCHAR(255) DEFAULT ''"),
            ("counterparty_iban", "ALTER TABLE transactions ADD COLUMN counterparty_iban VARCHAR(64) DEFAULT ''"),
            ("location", "ALTER TABLE transactions ADD COLUMN location VARCHAR(120) DEFAULT ''"),
            ("mcc", "ALTER TABLE transactions ADD COLUMN mcc VARCHAR(8)"),
            ("value_date", "ALTER TABLE transactions ADD COLUMN value_date DATE"),
            ("balance_after", "ALTER TABLE transactions ADD COLUMN balance_after FLOAT"),
            ("investment_activity", "ALTER TABLE transactions ADD COLUMN investment_activity VARCHAR(40)"),
            ("ticker", "ALTER TABLE transactions ADD COLUMN ticker VARCHAR(32)"),
            ("quantity", "ALTER TABLE transactions ADD COLUMN quantity FLOAT"),
            ("price_per_share", "ALTER TABLE transactions ADD COLUMN price_per_share FLOAT"),
            ("fx_rate", "ALTER TABLE transactions ADD COLUMN fx_rate FLOAT"),
        ]
        missing = [(name, sql) for name, sql in additions if name not in tx_cols]
        if missing:
            with engine.begin() as conn:
                for _, sql in missing:
                    conn.execute(text(sql))


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    ensure_all_household_defaults()
    db = SessionLocal()
    backfill_known_commerces(db)
    db.close()
    stop = asyncio.Event()
    worker = asyncio.create_task(_categorize_worker(stop))
    yield
    stop.set()
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)


async def _categorize_worker(stop: asyncio.Event) -> None:
    settings = get_settings()
    interval = max(0, int(settings.categorize_interval_seconds))
    if interval <= 0:
        logger.info("Periodic categorize disabled (CATEGORIZE_INTERVAL_SECONDS=%s)", interval)
        await stop.wait()
        return
    logger.info("Periodic categorize every %ss", interval)
    await asyncio.sleep(min(30, interval))
    while not stop.is_set():
        await asyncio.to_thread(categorize_all_households)
        slept = 0
        while slept < interval and not stop.is_set():
            step = min(5, interval - slept)
            await asyncio.sleep(step)
            slept += step

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


@app.get("/privacy", response_class=HTMLResponse)
def privacy() -> str:
    return PRIVACY_HTML


@app.get("/terms", response_class=HTMLResponse)
def terms() -> str:
    return TERMS_HTML
