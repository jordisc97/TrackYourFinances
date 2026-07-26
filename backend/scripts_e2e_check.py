import httpx
from pathlib import Path

base = "http://127.0.0.1:8000"
client = httpx.Client(base_url=base, timeout=30.0, follow_redirects=False)
login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password123"}).json()
headers = {"Authorization": f"Bearer {login['access_token']}"}
accounts = client.get("/api/accounts", headers=headers).json()
revolut = next(a for a in accounts if "Revolut" in a["name"])
files = {"file": ("sample_transactions.csv", Path("sample_transactions.csv").read_bytes(), "text/csv")}
data = {"account_id": str(revolut["id"])}
imp = client.post("/api/import/csv", headers=headers, data=data, files=files).json()
print("import", imp)
cats = {c["name"]: c["id"] for c in client.get("/api/categories", headers=headers).json()}
mapping = {
    "Salary": "Income",
    "Mercadona": "Food",
    "Metro": "Transport",
    "Netflix": "Subscriptions",
    "Rent": "Housing",
    "Restaurant": "Leisure",
    "ETF": "Investment",
    "Uber": "Transport",
    "Pharmacy": "Other",
    "Savings": "Transfer",
}
txs = client.get("/api/transactions?uncategorized=true", headers=headers).json()
for tx in txs:
    text = f"{tx['raw_description']} {tx['merchant']}"
    cat_name = "Other"
    for key, name in mapping.items():
        if key.lower() in text.lower():
            cat_name = name
            break
    client.post(f"/api/transactions/{tx['id']}/assign", headers=headers, json={"category_id": cats[cat_name], "create_rule": True})
dash = client.get("/api/dashboard?year=2026&month=7", headers=headers).json()
print("nw", dash["net_worth"], "income", dash["month"]["income"], "spend", dash["month"]["real_spend"], "save_pct", dash["month"]["save_pct"], "cats", len(dash["spend_by_category"]))
conn = client.post("/api/banking/connect/SABADELL_ES", headers=headers).json()
print("connect", conn)
cb = client.get(conn["authorization_url"].replace("localhost", "127.0.0.1"))
print("callback", cb.status_code, cb.headers.get("location"))
conns = client.get("/api/banking/connections", headers=headers).json()
print("connections", [(c["institution_name"], c["status"]) for c in conns])
sync = client.post(f"/api/banking/connections/{conns[-1]['id']}/sync", headers=headers).json()
print("sync", sync)
