<p align="center">
  <img src="docs/readme-banner.png" alt="TrackYourFinances — your wealth, simplified" width="100%" />
</p>

<h1 align="center">TrackYourFinances</h1>

<p align="center">
  <strong>Private household finance tracker</strong> for European banks — balances, cashflow, and AI-assisted insights in one place.
</p>

<p align="center">
  <a href="https://track-your-finances-yoxg.onrender.com/"><strong>Try the live app on Render →</strong></a>
</p>

<p align="center">
  <img alt="Stack" src="https://img.shields.io/badge/stack-FastAPI%20%7C%20React%20%7C%20SQLite-2ec4b6?style=for-the-badge&labelColor=0a0e14" />
  <img alt="Open Banking" src="https://img.shields.io/badge/open%20banking-GoCardless%20%2F%20Enable%20Banking-e8a87c?style=for-the-badge&labelColor=0a0e14" />
  <img alt="Self-hosted" src="https://img.shields.io/badge/deploy-self%20hosted-8b97a8?style=for-the-badge&labelColor=0a0e14" />
  <img alt="Render" src="https://img.shields.io/badge/deploy-Render-46E3B7?style=for-the-badge&labelColor=0a0e14" />
</p>

---

## Screenshots

Household auth, dashboard planning, money flow, CSV import, Open Banking, and partner invite — captured from the running app.

### Sign in / create household / join

<p align="center">
  <img src="docs/screenshots/auth.png" alt="Sign in, create household, or join with invite" width="80%" />
</p>

### Dashboard — month strategy & spend by category

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Dashboard with month-over-month wealth, spend/save/invest plan, and category benchmarks" width="80%" />
</p>

### Dashboard — advisor, investments & wealth forecast

<p align="center">
  <img src="docs/screenshots/dashboard-wealth.png" alt="Financial advisor chat, investment balances, and accumulated wealth forecast" width="80%" />
</p>

### Transactions — money flow & ledger

<p align="center">
  <img src="docs/screenshots/transactions.png" alt="Money flow graph and transaction ledger with categorize and split" width="80%" />
</p>

### Accounts & CSV / Excel import

<p align="center">
  <img src="docs/screenshots/accounts.png" alt="CSV and Excel import wizard with balances and manual accounts" width="80%" />
</p>

### Bank auto connection

<p align="center">
  <img src="docs/screenshots/banks.png" alt="Open Banking connect UI for Revolut and Sabadell" width="80%" />
</p>

### Profile & household invite

<p align="center">
  <img src="docs/screenshots/profile.png" alt="Profile settings and household invite code" width="80%" />
</p>

---

## Architecture

```mermaid
flowchart LR
  subgraph Client
    UI[Vite + React]
  end
  subgraph API
    FastAPI[FastAPI]
    Auth[JWT auth]
    Sync[Bank sync]
    AI[DeepSeek advisor]
  end
  subgraph Data
    DB[(SQLite)]
    CSV[CSV import]
  end
  subgraph Providers
    GC[GoCardless]
    EB[Enable Banking]
  end

  UI -->|REST /api| FastAPI
  FastAPI --> Auth
  FastAPI --> Sync
  FastAPI --> AI
  FastAPI --> DB
  CSV --> FastAPI
  Sync --> GC
  Sync --> EB
```

---

## Quick start

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

API · [http://127.0.0.1:8001](http://127.0.0.1:8001) · Docs · [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

### 2. Frontend

```powershell
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5174
```

App · [http://127.0.0.1:5174](http://127.0.0.1:5174) — register a household, then invite your partner from **Household**.

---

## Configuration

Copy `backend/.env.example` → `backend/.env` and fill only what you need.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing secret — use a long random string in any real deploy |
| `ENV` | `development` (local) or `production` (Render). Production refuses default secrets and hides `/docs` |
| `CORS_ORIGINS` | Comma-separated allowed origins. On Render, set to your public `https://….onrender.com` URL |
| `BANK_PROVIDER` | `gocardless` (default) or `enable_banking` |
| `GC_SECRET_ID` / `GC_SECRET_KEY` | GoCardless Bank Account Data credentials |
| `ENABLE_BANKING_APP_ID` / `ENABLE_BANKING_PRIVATE_KEY_PATH` | Enable Banking app + local PEM path |
| `DEEPSEEK_API` | Optional — powers advisor chat & smarter CSV mapping |

### Bank connection (GoCardless)

1. Sign up at [bankaccountdata.gocardless.com](https://bankaccountdata.gocardless.com/) and create `secret_id` / `secret_key`.
2. Put them in `backend/.env`:

```env
BANK_PROVIDER=gocardless
BANK_COUNTRY=ES
GC_SECRET_ID=your_secret_id
GC_SECRET_KEY=your_secret_key
GC_REDIRECT_URL=http://127.0.0.1:8001/api/banking/callback
```

Without GC keys, **Banks → Connect** uses a mock consent flow so you can still develop the UI.

For Enable Banking, set `BANK_PROVIDER=enable_banking` and the `ENABLE_BANKING_*` vars. Keep the PEM under `backend/keys/` (gitignored).

### CSV import

Use `backend/sample_transactions.csv` on **Transactions**.

Supported headers: `date` / `Fecha`, `amount` / `Importe`, `description` / `Concepto`, `merchant`, `external_id`.

### Sync CLI

```powershell
cd backend
.\.venv\Scripts\python.exe sync_cli.py
```

---

## Security (before you go public)

This repo is set up so **real credentials stay on your machine**:

| Path | Status |
|---|---|
| `backend/.env` | gitignored |
| `backend/keys/*.pem` | gitignored |
| `backend/data/*.db` | gitignored |
| `backend/.env.example` | safe placeholders only |

**Do not commit** API keys, private keys, or your SQLite database. Before publishing:

1. Confirm `git status` never lists `.env`, `*.pem`, or `*.db`
2. Rotate any key that ever lived in a committed file or chat history
3. Keep `SECRET_KEY` unique per environment

---

## Deploy on Render (free)

The repo includes a Docker image and [`render.yaml`](render.yaml) Blueprint that runs FastAPI + the built React app as one **free** web service.

1. Push this repo to GitHub and open [Render Blueprints](https://dashboard.render.com/blueprints).
2. Connect the repo and apply the Blueprint (`track-your-finances`).
3. Set **`CORS_ORIGINS`** to your public URL, e.g. `https://track-your-finances.onrender.com` (same value after the first deploy once the hostname is known).
4. Optional: set `DEEPSEEK_API` and bank provider secrets. For live banks, set redirect URLs to `https://<your-service>.onrender.com/api/banking/callback`.
5. Open the service URL — visitors register their own household (JWT + bcrypt).

**Free-tier tradeoffs:** the instance sleeps after idle time (first request can be slow), and SQLite lives on ephemeral disk — accounts/data are wiped on redeploy or when the free instance is recycled. Fine for demos; not for keeping real household history.

Local Docker smoke test:

```powershell
docker build -t track-your-finances .
docker run --rm -p 8000:8000 -e SECRET_KEY=local-docker-secret-change-me -e CORS_ORIGINS=http://127.0.0.1:8000 track-your-finances
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## Features

1. Household auth + invite code for a partner
2. Manual accounts / balance snapshots (brokers, crypto, cash)
3. CSV import + category assign (creates rules)
4. Bank connect via GoCardless or Enable Banking
5. Dashboard: net worth, spend %, save/invest targets, wealth charts
6. Optional DeepSeek advisor over your household transactions

---

<p align="center">
  <sub>Built for couples and households who want clarity without giving up privacy.</sub>
</p>
