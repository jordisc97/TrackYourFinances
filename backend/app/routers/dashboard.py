from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import DashboardOut, MonthlyStrategyIn, MonthlyStrategyOut
from app.services.dashboard import build_dashboard, get_or_create_strategy, strategy_out

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
