from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    DashboardOut,
    InvestmentRealIn,
    InvestmentRealOut,
    MonthlyStrategyIn,
    MonthlyStrategyOut,
    OpeningWealthIn,
    OpeningWealthOut,
    YearlyObjectiveIn,
    YearlyObjectiveOut,
)
from app.services.dashboard import build_dashboard, get_or_create_strategy, set_investment_real, set_opening_wealth, set_yearly_objective, strategy_out

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardOut:
    return build_dashboard(db, user.household_id, year, month)


@router.put("/strategy", response_model=MonthlyStrategyOut)
def update_strategy(
    payload: MonthlyStrategyIn,
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonthlyStrategyOut:
    row = get_or_create_strategy(db, user.household_id, year, month)
    row.spend_pct = payload.spend_pct
    row.save_pct = payload.save_pct
    row.invest_pct = payload.invest_pct
    db.commit()
    db.refresh(row)
    return strategy_out(row)


@router.put("/investment-real", response_model=InvestmentRealOut)
def update_investment_real(
    payload: InvestmentRealIn,
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvestmentRealOut:
    return set_investment_real(db, user.household_id, year, month, payload.real_value)


@router.put("/yearly-objective", response_model=YearlyObjectiveOut)
def update_yearly_objective(
    payload: YearlyObjectiveIn,
    year: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> YearlyObjectiveOut:
    row = set_yearly_objective(db, user.household_id, year, payload.target_net_worth)
    return YearlyObjectiveOut(year=row.year, target_net_worth=row.target_net_worth, forecast_year_end=None, actual_net_worth=None)


@router.put("/opening-wealth", response_model=OpeningWealthOut)
def update_opening_wealth(
    payload: OpeningWealthIn,
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OpeningWealthOut:
    return set_opening_wealth(db, user.household_id, year, month, payload.net_worth)
