# TrackYourFinances

Private household finance tracker for European banks (Revolut + Banco Sabadell first).

## Stack

- Backend: FastAPI + SQLite + SQLAlchemy
- Frontend: Vite + React + TypeScript + Recharts
- Open Banking: Enable Banking (mock mode without API keys)

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

### Enable Banking (live)

1. Create an app at https://enablebanking.com/
2. Put credentials in `backend/.env`:

```
ENABLE_BANKING_APP_ID=...
ENABLE_BANKING_PRIVATE_KEY_PATH=C:\path\to\private.pem
ENABLE_BANKING_REDIRECT_URL=http://localhost:8000/api/banking/callback
```

Without keys, **Banks → Connect** uses mock consent so you can develop the UI/flow.

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
4. Revolut / Sabadell connect via Enable Banking
5. Dashboard: net worth, spend %, save/invest allocation targets, wealth charts
