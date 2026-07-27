from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import AdvisorChatIn, AdvisorChatOut
from app.services.advisor import run_advisor_chat

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


@router.post("/chat", response_model=AdvisorChatOut)
def chat(payload: AdvisorChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AdvisorChatOut:
    return run_advisor_chat(db, user, payload)
