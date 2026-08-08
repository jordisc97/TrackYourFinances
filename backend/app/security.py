from datetime import datetime, timedelta
import re

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
PASSWORD_LETTER = re.compile(r"[A-Za-z]")
PASSWORD_DIGIT = re.compile(r"\d")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password(password: str) -> str | None:
    settings = get_settings()
    min_length = settings.min_password_length
    if len(password) < min_length:
        return f"Password must be at least {min_length} characters"
    if not PASSWORD_LETTER.search(password) or not PASSWORD_DIGIT.search(password):
        return "Password must include at least one letter and one digit"
    return None


def create_access_token(subject: str, extra: dict | None = None) -> str:
    settings = get_settings()
    payload = {"sub": subject, "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def decode_access_token_safe(token: str) -> dict | None:
    try:
        return decode_access_token(token)
    except JWTError:
        return None
