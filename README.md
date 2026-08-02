# TrackYourFinances

Private household finance tracker for European banks (Revolut + Banco Sabadell first).

## Stack

- Backend: FastAPI + SQLite + SQLAlchemy
- Frontend: Vite + React + TypeScript + Recharts
- Open Banking: GoCardless Bank Account Data (default; Enable Banking still available via env)

## Quick start

### Backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

### Frontend

```powershell
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5174
```

Open **http://127.0.0.1:5174** — register a household, invite your partner from **Household**.

API root: http://127.0.0.1:8001/ · docs: http://127.0.0.1:8001/docs

### Bank connection (GoCardless)

1. Sign up at https://bankaccountdata.gocardless.com/ and get `secret_id` / `secret_key`.
2. Put credentials in `backend/.env`:

```
BANK_PROVIDER=gocardless
BANK_COUNTRY=ES
GC_SECRET_ID=...
GC_SECRET_KEY=...
GC_REDIRECT_URL=http://127.0.0.1:8001/api/banking/callback
```

Without GC keys, **Banks → Connect** uses mock consent so you can develop the UI/flow.

To use Enable Banking instead, set `BANK_PROVIDER=enable_banking` and the existing `ENABLE_BANKING_*` vars.

### CSV import

Use `backend/sample_transactions.csv` on **Transactions**. Supported headers: `date`/`Fecha`, `amount`/`Importe`, `description`/`Concepto`, `merchant`, `external_id`.

### Sync CLI

```powershell
cd backend
.\.venv\Scripts\python.exe sync_cli.py
```

## Features

1. Household auth + invite code for partner
2. Manual accounts / balance snapshots (brokers, crypto, etc.)
3. CSV import + category assign (creates rules)
4. Bank connect via GoCardless (or Enable Banking via `BANK_PROVIDER`)
5. Dashboard: net worth, spend %, save/invest allocation targets, wealth charts
