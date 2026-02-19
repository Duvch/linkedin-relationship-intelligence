import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.database import SessionLocal
from app.models import Settings, Notification

logger = logging.getLogger(__name__)


def _get_setting(db, key: str, default: str = "", user_id: int = None) -> str:
    q = db.query(Settings).filter(Settings.key == key)
    if user_id is not None:
        q = q.filter(Settings.user_id == user_id)
    row = q.first()
    return row.value if row and row.value else default


def get_email_settings(user_id: int = None) -> dict:
    db = SessionLocal()
    try:
        return {
            "notify_email": _get_setting(db, "notify_email", user_id=user_id),
            "smtp_host": _get_setting(db, "smtp_host", "smtp.gmail.com", user_id=user_id),
            "smtp_port": _get_setting(db, "smtp_port", "587", user_id=user_id),
            "smtp_user": _get_setting(db, "smtp_user", user_id=user_id),
            "smtp_password": _get_setting(db, "smtp_password", user_id=user_id),
        }
    finally:
        db.close()


def save_email_settings(user_id: int, notify_email: str, smtp_host: str, smtp_port: str, smtp_user: str, smtp_password: str):
    db = SessionLocal()
    try:
        settings = {
            "notify_email": notify_email,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
        }
        if smtp_password:
            settings["smtp_password"] = smtp_password
        for key, value in settings.items():
            row = db.query(Settings).filter(Settings.key == key, Settings.user_id == user_id).first()
            if row:
                row.value = value
            else:
                db.add(Settings(key=key, value=value, user_id=user_id))
        db.commit()
        logger.info(f"Email settings saved for user {user_id}.")
    finally:
        db.close()


def save_notification(title: str, body: str, notif_type: str = "digest", user_id: int = None):
    db = SessionLocal()
    try:
        notif = Notification(title=title, body=body, type=notif_type, user_id=user_id)
        db.add(notif)
        db.commit()
        logger.info(f"Notification saved: {title} (user_id={user_id})")
    finally:
        db.close()


def get_notifications(limit: int = 50, user_id: int = None):
    db = SessionLocal()
    try:
        q = db.query(Notification)
        if user_id is not None:
            q = q.filter(Notification.user_id == user_id)
        return q.order_by(Notification.created_at.desc()).limit(limit).all()
    finally:
        db.close()


def mark_notification_read(notif_id: int, user_id: int = None):
    db = SessionLocal()
    try:
        q = db.query(Notification).filter(Notification.id == notif_id)
        if user_id is not None:
            q = q.filter(Notification.user_id == user_id)
        notif = q.first()
        if notif:
            notif.is_read = 1
            db.commit()
    finally:
        db.close()


def mark_all_read(user_id: int = None):
    db = SessionLocal()
    try:
        q = db.query(Notification).filter(Notification.is_read == 0)
        if user_id is not None:
            q = q.filter(Notification.user_id == user_id)
        q.update({"is_read": 1})
        db.commit()
    finally:
        db.close()


def get_unread_count(user_id: int = None) -> int:
    db = SessionLocal()
    try:
        q = db.query(Notification).filter(Notification.is_read == 0)
        if user_id is not None:
            q = q.filter(Notification.user_id == user_id)
        return q.count()
    finally:
        db.close()


def send_digest(entries: list[dict], profile_names: list[str] | None = None, user_id: int = None) -> bool:
    if entries:
        title = f"Daily Update - {len(entries)} new post(s)"
        body_parts = []
        for e in entries:
            line = f"{e.get('name', 'Unknown')} [{e.get('category', 'Other')}]: {e.get('summary', 'N/A')}"
            post_url = e.get('post_url', '')
            if post_url:
                line += f"\n{post_url}"
            body_parts.append(line)
        body = "\n\n".join(body_parts)
    else:
        names = ", ".join(profile_names) if profile_names else "your tracked profiles"
        title = "Daily Update - No new posts today"
        body = f"No new posts were found from {names}. We'll check again tomorrow!"

    save_notification(title, body, user_id=user_id)

    settings = get_email_settings(user_id=user_id)
    notify_email = settings["notify_email"]
    smtp_host = settings["smtp_host"]
    smtp_port = int(settings["smtp_port"])
    smtp_user = settings["smtp_user"]
    smtp_password = settings["smtp_password"]

    if not notify_email or not smtp_user or not smtp_password:
        logger.info("Email not fully configured. Notification saved to dashboard only.")
        return True

    if entries:
        html_body = _build_html(entries)
        plain_body = _build_plain_text(entries)
        subject = f"Daily Relationship Update - {len(entries)} new post(s)"
    else:
        names = ", ".join(profile_names) if profile_names else "your tracked profiles"
        subject = "Daily Relationship Update - No new posts today"
        plain_body = f"No new posts were found today from {names}.\nWe'll check again tomorrow!"
        html_body = f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f0f2f5; padding:20px;">
        <div style="max-width:600px; margin:0 auto; background:white; border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <div style="background:#0a66c2; color:white; padding:20px 24px;">
                <h1 style="margin:0; font-size:20px;">Daily Relationship Update</h1>
                <p style="margin:4px 0 0; opacity:0.9; font-size:14px;">No new posts today</p>
            </div>
            <div style="padding:32px 24px; text-align:center;">
                <p style="font-size:16px; color:#333; margin:0 0 8px;">No new posts were found from {names}.</p>
                <p style="font-size:14px; color:#888; margin:0;">We'll check again tomorrow!</p>
            </div>
            <div style="padding:16px 24px; text-align:center; color:#999; font-size:12px;">
                LinkedIn Relationship Intelligence Tool
            </div>
        </div>
    </body>
    </html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = notify_email

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, notify_email, msg.as_string())
        logger.info(f"Email digest sent to {notify_email} with {len(entries)} entries.")
        return True
    except Exception as e:
        logger.error(f"Failed to send email (notification still saved to dashboard): {e}")
        return False


def _build_plain_text(entries: list[dict]) -> str:
    lines = ["Daily Relationship Update", "=" * 30, ""]
    for entry in entries:
        lines.append(f"Name: {entry.get('name', 'Unknown')}")
        lines.append(f"Category: {entry.get('category', 'Other')}")
        lines.append(f"Summary: {entry.get('summary', 'N/A')}")
        lines.append(f"Suggested Reply: {entry.get('suggested_reply', 'N/A')}")
        lines.append(f"Post Link: {entry.get('post_url', 'N/A')}")
        lines.append("-" * 30)
        lines.append("")
    return "\n".join(lines)


def _build_html(entries: list[dict]) -> str:
    category_colors = {
        "Funding": "#2e7d32",
        "Hiring": "#e65100",
        "Launch": "#1565c0",
        "Other": "#616161",
    }

    rows = ""
    for entry in entries:
        name = entry.get("name", "Unknown")
        category = entry.get("category", "Other")
        summary = entry.get("summary", "N/A")
        reply = entry.get("suggested_reply", "N/A")
        post_url = entry.get("post_url", "")
        color = category_colors.get(category, "#616161")

        link_html = f'<a href="{post_url}" style="color:#0a66c2;">View Post</a>' if post_url else "N/A"

        rows += f"""
        <tr>
            <td style="padding:16px; border-bottom:1px solid #eee;">
                <div style="font-weight:600; font-size:15px; margin-bottom:6px;">{name}</div>
                <div style="display:inline-block; background:{color}; color:white; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600; margin-bottom:8px;">{category}</div>
                <div style="font-size:14px; color:#333; margin-bottom:8px;">{summary}</div>
                <div style="background:#f8f9fa; border-left:3px solid #0a66c2; padding:8px 12px; font-size:13px; color:#555; margin-bottom:8px;">
                    <strong style="color:#0a66c2; font-size:11px; text-transform:uppercase;">Suggested Reply</strong><br>{reply}
                </div>
                <div>{link_html}</div>
            </td>
        </tr>"""

    return f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f0f2f5; padding:20px;">
        <div style="max-width:600px; margin:0 auto; background:white; border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <div style="background:#0a66c2; color:white; padding:20px 24px;">
                <h1 style="margin:0; font-size:20px;">Daily Relationship Update</h1>
                <p style="margin:4px 0 0; opacity:0.9; font-size:14px;">{len(entries)} new post(s) detected</p>
            </div>
            <table style="width:100%; border-collapse:collapse;">
                {rows}
            </table>
            <div style="padding:16px 24px; text-align:center; color:#999; font-size:12px;">
                LinkedIn Relationship Intelligence Tool
            </div>
        </div>
    </body>
    </html>"""
