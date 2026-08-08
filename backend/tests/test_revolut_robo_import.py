import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Account, AccountType, Category, Household, InvestmentHolding, Transaction, TransactionSource
from app.seed import seed_household_defaults
from app.services.dashboard import account_balance_on, invest_amount, month_flow_totals
from app.services.flow import build_account_flow
from app.services.revolut_robo_import import (
    ACTIVITY_BUY,
    ACTIVITY_CASH_TOP_UP,
    ACTIVITY_DIVIDEND,
    ACTIVITY_FEE,
    import_revolut_robo_csv,
    parse_money_field,
    parse_revolut_row,
    preview_revolut_robo_csv,
)


SAMPLE_CSV = """Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
2024-02-23T13:37:45.930694Z,,CASH TOP-UP,,,EUR 100,EUR,1.0000
2024-02-26T10:30:04.171Z,IS3C,BUY - MARKET,0.07548104,EUR 66.24,EUR 5,EUR,1.0000
2024-02-26T10:30:05.402Z,DBXJ,BUY - MARKET,0.06773984,EUR 73.81,EUR 5,EUR,1.0000
2024-03-03T10:00:00.000Z,,CASH TOP-UP,,,EUR 100,EUR,1.0000
2024-03-04T10:00:00.000Z,IS3C,BUY - MARKET,0.15,EUR 66.24,EUR 100,EUR,1.0000
2024-03-18T15:41:17.144472Z,EXI2,DIVIDEND,,,EUR 0.04,EUR,1.0000
2024-03-23T10:01:35.512968Z,,ROBO MANAGEMENT FEE,,,EUR -0.10,EUR,1.0000
2024-03-26T09:00:00.000Z,,CASH TOP-UP,,,EUR 100,EUR,1.0000
2024-03-27T10:00:00.000Z,DBXJ,BUY - MARKET,0.1,EUR 73.81,EUR 100,EUR,1.0000
"""


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    household = Household(name="Test", invite_code="testcode1")
    session.add(household)
    session.flush()
    seed_household_defaults(session, household)
    checking = Account(household_id=household.id, name="Everyday checking", account_type=AccountType.checking.value, currency="EUR")
    invest = Account(household_id=household.id, name="Revolut Robo", account_type=AccountType.investment.value, currency="EUR")
    session.add_all([checking, invest])
    session.commit()
    yield session, household, checking, invest
    session.close()


def test_parse_money_and_negative_fee():
    assert parse_money_field("EUR 100").amount == 100.0
    assert parse_money_field("EUR 100").currency == "EUR"
    assert parse_money_field("EUR -0.10").amount == -0.10
    assert parse_money_field("EUR -0.10").currency == "EUR"


def test_parse_revolut_row_iso_and_empty_fields():
    row = {
        "Date": "2024-02-23T13:37:45.930694Z",
        "Ticker": "",
        "Type": "CASH TOP-UP",
        "Quantity": "",
        "Price per share": "",
        "Total Amount": "EUR 100",
        "Currency": "EUR",
        "FX Rate": "1.0000",
    }
    parsed = parse_revolut_row(row)
    assert parsed.booked_at.isoformat() == "2024-02-23"
    assert parsed.ticker == ""
    assert parsed.quantity is None
    assert parsed.price_per_share is None
    assert parsed.fx_rate == 1.0
    assert parsed.activity == ACTIVITY_CASH_TOP_UP
    assert parsed.total_amount == 100.0


def test_parse_buy_classification():
    row = {
        "Date": "2024-02-26T10:30:04.171Z",
        "Ticker": "IS3C",
        "Type": "BUY - MARKET",
        "Quantity": "0.07548104",
        "Price per share": "EUR 66.24",
        "Total Amount": "EUR 5",
        "Currency": "EUR",
        "FX Rate": "1.0000",
    }
    parsed = parse_revolut_row(row)
    assert parsed.activity == ACTIVITY_BUY
    assert parsed.ticker == "IS3C"
    assert parsed.quantity == pytest.approx(0.07548104)
    assert parsed.price_per_share == pytest.approx(66.24)
    assert parsed.balance_amount == 0.0


def test_preview_summary_counts():
    summary = preview_revolut_robo_csv(SAMPLE_CSV.encode("utf-8"))
    assert summary.format_detected == "Revolut Robo-Advisor"
    assert summary.transactions == 9
    assert summary.contributions == 300.0
    assert summary.purchases == pytest.approx(210.0)
    assert summary.dividends == pytest.approx(0.04)
    assert summary.management_fees == pytest.approx(-0.10)
    assert summary.securities == 3
    assert summary.currency == "EUR"


def test_import_classifies_activities(db):
    session, _household, _checking, invest = db
    imported, skipped, replaced, categorized, summary = import_revolut_robo_csv(session, invest, SAMPLE_CSV.encode("utf-8"))
    assert imported == 9
    assert skipped == 0
    assert replaced == 0
    assert categorized == 9
    assert summary.contributions == 300.0
    txs = session.query(Transaction).filter(Transaction.account_id == invest.id).all()
    assert ACTIVITY_CASH_TOP_UP in {tx.investment_activity for tx in txs}
    assert ACTIVITY_BUY in {tx.investment_activity for tx in txs}
    assert ACTIVITY_DIVIDEND in {tx.investment_activity for tx in txs}
    assert ACTIVITY_FEE in {tx.investment_activity for tx in txs}
    fee = next(tx for tx in txs if tx.investment_activity == ACTIVITY_FEE)
    assert fee.amount == pytest.approx(-0.10)
    holdings = {h.ticker: h.quantity for h in session.query(InvestmentHolding).filter(InvestmentHolding.account_id == invest.id).all()}
    assert holdings["IS3C"] == pytest.approx(0.07548104 + 0.15)
    assert holdings["DBXJ"] == pytest.approx(0.06773984 + 0.1)


def test_monthly_investment_excludes_buys(db):
    session, household, _checking, invest = db
    import_revolut_robo_csv(session, invest, SAMPLE_CSV.encode("utf-8"))
    feb = [tx for tx in session.query(Transaction).filter(Transaction.account_id == invest.id).all() if tx.booked_at.year == 2024 and tx.booked_at.month == 2]
    mar = [tx for tx in session.query(Transaction).filter(Transaction.account_id == invest.id).all() if tx.booked_at.year == 2024 and tx.booked_at.month == 3]
    assert round(abs(sum(invest_amount(tx) for tx in feb)), 2) == 100.0
    assert round(abs(sum(invest_amount(tx) for tx in mar)), 2) == 200.0
    _, _, invest_out_feb, _ = month_flow_totals(feb)
    _, _, invest_out_mar, _ = month_flow_totals(mar)
    assert invest_out_feb == 100.0
    assert invest_out_mar == 200.0
    assert household.id


def test_duplicate_ticker_buys_single_holding(db):
    session, _household, _checking, invest = db
    csv_text = """Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
2024-02-26T10:30:04.171Z,DBXJ,BUY - MARKET,0.06653137,EUR 73.81,EUR 5,EUR,1.0000
2024-02-26T10:30:05.402Z,DBXJ,BUY - MARKET,0.01,EUR 73.81,EUR 1,EUR,1.0000
"""
    imported, skipped, *_rest = import_revolut_robo_csv(session, invest, csv_text.encode("utf-8"))
    assert imported == 2
    assert skipped == 0
    holdings = session.query(InvestmentHolding).filter(InvestmentHolding.account_id == invest.id, InvestmentHolding.ticker == "DBXJ").all()
    assert len(holdings) == 1
    assert holdings[0].quantity == pytest.approx(0.07653137)


def test_duplicate_import_skips(db):
    session, _household, _checking, invest = db
    first = import_revolut_robo_csv(session, invest, SAMPLE_CSV.encode("utf-8"))
    second = import_revolut_robo_csv(session, invest, SAMPLE_CSV.encode("utf-8"))
    assert first[0] == 9
    assert second[0] == 0
    assert second[1] == 9
    assert session.query(Transaction).filter(Transaction.account_id == invest.id).count() == 9
    assert session.query(InvestmentHolding).filter(InvestmentHolding.account_id == invest.id).count() == 2


def test_buy_does_not_reduce_contributed_balance(db):
    session, _household, _checking, invest = db
    import_revolut_robo_csv(session, invest, SAMPLE_CSV.encode("utf-8"))
    balance = account_balance_on(session, invest.id, date_from_iso("2024-03-31"))
    assert balance == pytest.approx(100 + 100 + 0.04 - 0.10 + 100)


def test_money_flow_and_no_double_count(db):
    session, household, checking, invest = db
    investment_cat = session.query(Category).filter(Category.household_id == household.id, Category.name == "Investment").first()
    session.add(
        Transaction(
            account_id=checking.id,
            category_id=investment_cat.id,
            booked_at=date_from_iso("2024-02-23"),
            amount=-100.0,
            currency="EUR",
            raw_description="Transfer to Revolut Robo",
            merchant="Revolut",
            source=TransactionSource.manual.value,
        )
    )
    session.commit()
    import_revolut_robo_csv(session, invest, SAMPLE_CSV.encode("utf-8"))
    checking_tx = session.query(Transaction).filter(Transaction.account_id == checking.id).one()
    assert checking_tx.category.kind == "transfer"
    feb_txs = [tx for tx in session.query(Transaction).all() if tx.booked_at.year == 2024 and tx.booked_at.month == 2]
    _, _, invest_out, _ = month_flow_totals(feb_txs)
    assert invest_out == 100.0
    flow = build_account_flow(session, household.id, 2024, 2)
    invest_edges = [edge for edge in flow.edges if edge.kind == "invest"]
    assert any(edge.amount == 100.0 for edge in invest_edges)


def test_money_flow_infers_funding_for_cash_top_up(db):
    session, household, checking, invest = db
    income = session.query(Category).filter(Category.household_id == household.id, Category.name == "Income").first()
    session.add(
        Transaction(
            account_id=checking.id,
            category_id=income.id,
            booked_at=date_from_iso("2024-02-01"),
            amount=5000.0,
            currency="EUR",
            raw_description="Salary",
            merchant="Employer",
            source=TransactionSource.manual.value,
        )
    )
    session.commit()
    top_up_only = """Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
2024-02-23T13:37:45.930694Z,,CASH TOP-UP,,,EUR 282.10,EUR,1.0000
"""
    import_revolut_robo_csv(session, invest, top_up_only.encode("utf-8"))
    flow = build_account_flow(session, household.id, 2024, 2)
    invest_edges = [edge for edge in flow.edges if edge.kind == "invest"]
    assert len(invest_edges) == 1
    assert invest_edges[0].amount == pytest.approx(282.10)
    assert invest_edges[0].source == "income"
    assert invest_edges[0].target == f"account-{invest.id}"
    income_to_checking = next(edge for edge in flow.edges if edge.kind == "income" and edge.target == f"account-{checking.id}")
    assert income_to_checking.amount == pytest.approx(5000.0 - 282.10)
    invest_node = next(node for node in flow.nodes if node.account_id == invest.id)
    assert invest_node.amount == pytest.approx(282.10)


def test_unmatched_checking_investment_not_double_counted(db):
    session, household, checking, invest = db
    investment_cat = session.query(Category).filter(Category.household_id == household.id, Category.name == "Investment").first()
    session.add(
        Transaction(
            account_id=checking.id,
            category_id=investment_cat.id,
            booked_at=date_from_iso("2024-02-23"),
            amount=-100.0,
            currency="EUR",
            raw_description="Broker purchase",
            merchant="Other broker",
            source=TransactionSource.manual.value,
        )
    )
    session.commit()
    top_up_only = """Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
2024-02-23T13:37:45.930694Z,,CASH TOP-UP,,,EUR 100,EUR,1.0000
"""
    import_revolut_robo_csv(session, invest, top_up_only.encode("utf-8"))
    checking_tx = session.query(Transaction).filter(Transaction.account_id == checking.id).one()
    assert checking_tx.category.kind == "investment"
    feb_txs = [tx for tx in session.query(Transaction).all() if tx.booked_at.year == 2024 and tx.booked_at.month == 2]
    _, _, invest_out, _ = month_flow_totals(feb_txs)
    assert invest_out == 100.0


def date_from_iso(value: str):
    from datetime import date
    return date.fromisoformat(value)
