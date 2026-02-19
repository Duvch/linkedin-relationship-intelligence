import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

import csv
import io

from sqlalchemy import or_, and_

from fastapi import FastAPI, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import init_db, get_db, SessionLocal
from app.models import Profile, Post, Notification, User, Settings
from app.scheduler import start_scheduler, run_daily_job
from app.auth import (
    create_session_token, find_or_create_user,
    get_current_user, require_user, COOKIE_NAME
)

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    logger.info("Application started successfully.")
    yield
    logger.info("Application shutting down.")


app = FastAPI(
    title="LinkedIn Relationship Intelligence",
    description="Internal tool for tracking LinkedIn profiles and generating relationship insights.",
    version="1.0.0",
    lifespan=lifespan,
)

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

app.add_middleware(NoCacheStaticMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class ProfileCreate(BaseModel):
    name: str
    linkedin_url: str


class ProfileResponse(BaseModel):
    id: int
    name: str
    linkedin_url: str
    type: str
    created_at: datetime

    class Config:
        from_attributes = True


class PostResponse(BaseModel):
    id: int
    profile_id: int
    post_text: str
    post_url: str | None
    post_timestamp: datetime | None
    summary: str | None
    category: str | None
    suggested_reply: str | None
    created_at: datetime

    class Config:
        from_attributes = True


def _read_template(name: str) -> str:
    html_path = BASE_DIR / "templates" / name
    try:
        return html_path.read_text()
    except FileNotFoundError:
        return f"<h1>Template '{name}' not found</h1>"


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user = get_current_user(request)
    if not user:
        return HTMLResponse(
            content=_read_template("login.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return HTMLResponse(
        content=_read_template("dashboard.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.post("/enter")
async def enter_submit(request: Request):
    form = await request.form()
    name = form.get("name", "").strip()

    if not name:
        return HTMLResponse(
            content=_read_template("login.html").replace(
                "<!--ERROR-->",
                '<div class="auth-error">Please enter your name.</div>'
            ),
            status_code=400,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    user = find_or_create_user(name)
    token = create_session_token(user.id)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=60*60*24*365)
    return response


@app.get("/switch-user")
def switch_user():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/api/me")
def get_me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/profiles", response_model=ProfileResponse)
def create_profile(profile: ProfileCreate, request: Request, db: Session = Depends(get_db)):
    user = require_user(request)

    existing = db.query(Profile).filter(
        Profile.linkedin_url == profile.linkedin_url,
        Profile.user_id == user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You already track this LinkedIn profile.")

    new_profile = Profile(
        user_id=user.id,
        name=profile.name,
        linkedin_url=profile.linkedin_url,
        type="person",
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    logger.info(f"Created profile: {new_profile.name} for user {user.display_name}")
    return new_profile


@app.post("/profiles/upload-csv")
async def upload_csv(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = require_user(request)

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    try:
        content = await file.read()
        text = content.decode("utf-8-sig")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read the file. Make sure it's a valid CSV.")

    reader = csv.DictReader(io.StringIO(text))

    fieldnames = reader.fieldnames or []
    lower_fields = [f.lower().strip() for f in fieldnames]

    name_col = None
    url_col = None

    for i, f in enumerate(lower_fields):
        if f in ("name", "full name", "fullname", "person", "company name"):
            name_col = fieldnames[i]
        elif f in ("linkedin_url", "linkedin url", "url", "linkedin", "profile url", "profile_url", "linkedin profile", "linkedin_profile"):
            url_col = fieldnames[i]

    if not name_col or not url_col:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have 'name' and 'linkedin_url' columns. Found columns: {', '.join(fieldnames)}"
        )

    added = 0
    skipped = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        name = (row.get(name_col) or "").strip()
        linkedin_url = (row.get(url_col) or "").strip()

        if not name or not linkedin_url:
            skipped += 1
            continue

        if not linkedin_url.startswith("http"):
            linkedin_url = "https://" + linkedin_url

        existing = db.query(Profile).filter(
            Profile.linkedin_url == linkedin_url,
            Profile.user_id == user.id
        ).first()
        if existing:
            skipped += 1
            continue

        try:
            new_profile = Profile(
                user_id=user.id,
                name=name,
                linkedin_url=linkedin_url,
                type="person",
            )
            db.add(new_profile)
            db.commit()
            added += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Row {row_num}: {str(e)}")

    logger.info(f"CSV upload by {user.display_name}: {added} added, {skipped} skipped")
    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "message": f"Imported {added} profile(s). {skipped} skipped (duplicates or empty rows)."
    }


@app.get("/profiles", response_model=list[ProfileResponse])
def list_profiles(request: Request, db: Session = Depends(get_db)):
    user = require_user(request)
    return db.query(Profile).filter(Profile.user_id == user.id).all()


@app.get("/profiles/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request)
    profile = db.query(Profile).filter(Profile.id == profile_id, Profile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


@app.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request)
    profile = db.query(Profile).filter(Profile.id == profile_id, Profile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    db.delete(profile)
    db.commit()
    logger.info(f"Deleted profile: {profile.name} for user {user.display_name}")
    return {"message": f"Profile '{profile.name}' deleted."}


@app.get("/profiles/{profile_id}/posts", response_model=list[PostResponse])
def get_profile_posts(profile_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request)
    profile = db.query(Profile).filter(Profile.id == profile_id, Profile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return db.query(Post).filter(
        Post.profile_id == profile_id,
        or_(
            Post.post_timestamp >= cutoff,
            and_(Post.post_timestamp.is_(None), Post.created_at >= cutoff)
        )
    ).order_by(Post.created_at.desc()).all()


@app.get("/posts", response_model=list[PostResponse])
def list_all_posts(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    user = require_user(request)
    user_profile_ids = [p.id for p in db.query(Profile).filter(Profile.user_id == user.id).all()]
    if not user_profile_ids:
        return []
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return db.query(Post).filter(
        Post.profile_id.in_(user_profile_ids),
        or_(
            Post.post_timestamp >= cutoff,
            and_(Post.post_timestamp.is_(None), Post.created_at >= cutoff)
        )
    ).order_by(Post.created_at.desc()).limit(limit).all()


@app.post("/trigger-job")
def trigger_daily_job(request: Request):
    user = require_user(request)
    try:
        run_daily_job(user_id=user.id)
        return {"message": "Daily job triggered successfully."}
    except Exception as e:
        logger.error(f"Manual job trigger failed: {e}")
        raise HTTPException(status_code=500, detail=f"Job failed: {str(e)}")


class EmailSettingsRequest(BaseModel):
    notify_email: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: str = "587"
    smtp_user: str = ""
    smtp_password: str = ""


@app.get("/settings/email")
def get_settings(request: Request):
    user = require_user(request)
    from app.notify import get_email_settings
    settings = get_email_settings(user_id=user.id)
    if settings.get("smtp_password"):
        settings["smtp_password"] = "***configured***"
    return settings


@app.post("/settings/email")
def update_settings(data: EmailSettingsRequest, request: Request):
    user = require_user(request)
    from app.notify import save_email_settings
    save_email_settings(
        user_id=user.id,
        notify_email=data.notify_email,
        smtp_host=data.smtp_host,
        smtp_port=data.smtp_port,
        smtp_user=data.smtp_user,
        smtp_password=data.smtp_password,
    )
    return {"message": "Email settings saved successfully."}


@app.get("/settings/linkedin")
def get_linkedin_settings(request: Request):
    require_user(request)
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    return {
        "linkedin_configured": bool(api_key),
        "auth_method": "rapidapi" if api_key else "none",
    }


@app.get("/notifications")
def list_notifications(request: Request, limit: int = 50):
    user = require_user(request)
    from app.notify import get_notifications
    notifs = get_notifications(limit, user_id=user.id)
    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "type": n.type,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]


@app.get("/notifications/unread-count")
def unread_count(request: Request):
    user = require_user(request)
    from app.notify import get_unread_count
    return {"count": get_unread_count(user_id=user.id)}


@app.post("/notifications/mark-read/{notif_id}")
def mark_read(notif_id: int, request: Request):
    user = require_user(request)
    from app.notify import mark_notification_read
    mark_notification_read(notif_id, user_id=user.id)
    return {"message": "Marked as read."}


@app.post("/notifications/mark-all-read")
def mark_all_notifications_read(request: Request):
    user = require_user(request)
    from app.notify import mark_all_read
    mark_all_read(user_id=user.id)
    return {"message": "All notifications marked as read."}
