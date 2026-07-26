from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import IncomeAllocationPlan, User
from app.schemas import AllocationPlanIn, AllocationPlanOut, DashboardOut
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardOut:
    return build_dashboard(db, user.household_id, year, month)


@router.put("/allocation", response_model=AllocationPlanOut)
def update_allocation(payload: AllocationPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> IncomeAllocationPlan:
    plan = db.query(IncomeAllocationPlan).filter(IncomeAllocationPlan.household_id == user.household_id).one()
    plan.spend_pct = payload.spend_pct
    plan.save_pct = payload.save_pct
    plan.invest_pct = payload.invest_pct
    db.commit()
    db.refresh(plan)
    return plan
