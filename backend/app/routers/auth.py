from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Household, User, UserRole
from app.schemas import HouseholdOut, JoinHouseholdIn, LoginIn, ProfileUpdateIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password
from app.seed import new_invite_code, seed_household_defaults
from app.services.benchmarks import invalidate_benchmarks, refresh_location_benchmarks
from app.services.dashboard import average_income_spend

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    household = Household(name=payload.household_name, invite_code=new_invite_code())
    db.add(household)
    db.flush()
    seed_household_defaults(db, household)
    user = User(household_id=household.id, email=payload.email.lower(), hashed_password=hash_password(payload.password), display_name=payload.display_name, role=UserRole.owner.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(str(user.id), {"household_id": household.id}))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenOut(access_token=create_access_token(str(user.id), {"household_id": user.household_id}))


@router.post("/join", response_model=TokenOut)
def join_household(payload: JoinHouseholdIn, db: Session = Depends(get_db)) -> TokenOut:
    household = db.query(Household).filter(Household.invite_code == payload.invite_code).first()
    if household is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found")
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(household_id=household.id, email=payload.email.lower(), hashed_password=hash_password(payload.password), display_name=payload.display_name, role=UserRole.member.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(str(user.id), {"household_id": household.id}))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/household", response_model=HouseholdOut)
def household(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Household:
    return db.get(Household, user.household_id)


@router.put("/profile", response_model=HouseholdOut)
def update_profile(payload: ProfileUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Household:
    household = db.get(Household, user.household_id)
    location_changed = False
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip() or user.display_name
    if payload.household_name is not None:
        household.name = payload.household_name.strip() or household.name
    if payload.location is not None:
        new_location = payload.location.strip()
        location_changed = new_location != (household.location or "")
        household.location = new_location
    db.commit()
    db.refresh(household)
    db.refresh(user)
    if location_changed:
        invalidate_benchmarks(db, household.id)
        avg_income, _ = average_income_spend(db, household.id)
        refresh_location_benchmarks(db, household, avg_income)
    return household
