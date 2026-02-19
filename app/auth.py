import os
import logging
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.models import User

logger = logging.getLogger(__name__)

SECRET_KEY = os.environ.get("SESSION_SECRET")
if not SECRET_KEY:
    raise RuntimeError("SESSION_SECRET environment variable must be set")

serializer = URLSafeTimedSerializer(SECRET_KEY)
COOKIE_NAME = "session_token"
TOKEN_MAX_AGE = 60 * 60 * 24 * 365


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def get_user_id_from_token(token: str) -> int | None:
    try:
        data = serializer.loads(token, max_age=TOKEN_MAX_AGE)
        return data.get("user_id")
    except Exception:
        return None


def get_current_user(request: Request) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = get_user_id_from_token(token)
    if not user_id:
        return None
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return user
    finally:
        db.close()


def require_user(request: Request) -> User:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def find_or_create_user(name: str) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == name.lower().strip()).first()
        if user:
            return user
        new_user = User(
            username=name.lower().strip(),
            display_name=name.strip(),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"Created new user: {new_user.display_name}")
        return new_user
    finally:
        db.close()
