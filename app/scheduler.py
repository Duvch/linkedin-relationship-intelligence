import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import or_
from app.database import SessionLocal
from app.models import Profile, Post, User
from app.linkedin import get_recent_posts
from app.ai import analyze_post
from app.notify import send_digest

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def run_daily_job(user_id: int = None):
    logger.info(f"Starting daily relationship intelligence job (user_id={user_id})...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_daily_job(user_id=user_id))
    except Exception as e:
        logger.error(f"Daily job failed: {e}", exc_info=True)
    finally:
        loop.close()


def run_all_users_job():
    logger.info("Running scheduled daily job for all users...")
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            logger.info("No users found. Skipping scheduled job.")
            return
        for user in users:
            try:
                run_daily_job(user_id=user.id)
            except Exception as e:
                logger.error(f"Job failed for user {user.username}: {e}", exc_info=True)
    finally:
        db.close()


async def _daily_job(user_id: int = None):
    db = SessionLocal()
    try:
        q = db.query(Profile)
        if user_id is not None:
            q = q.filter(Profile.user_id == user_id)
        profiles = q.all()

        if not profiles:
            logger.info("No profiles found. Skipping daily job.")
            return

        logger.info(f"Processing {len(profiles)} profiles...")
        digest_entries = []

        for profile in profiles:
            logger.info(f"Fetching posts for: {profile.name}")

            if not profile.linkedin_url:
                logger.warning(f"No LinkedIn URL for {profile.name}, skipping.")
                continue

            posts = await get_recent_posts(profile.linkedin_url)
            cutoff = datetime.utcnow() - timedelta(hours=24)

            for post_data in posts:
                post_ts = post_data.get("post_timestamp")
                if post_ts and post_ts < cutoff:
                    logger.debug(f"Skipping old post for {profile.name} (posted {post_ts})")
                    continue

                post_text = post_data["post_text"]
                post_url = post_data["post_url"]
                content_hash = hashlib.sha256(
                    f"{profile.id}:{post_text[:500]}".encode()
                ).hexdigest()

                existing = db.query(Post).filter(
                    Post.profile_id == profile.id,
                    or_(
                        Post.post_url == post_url if post_url else False,
                        Post.post_hash == content_hash,
                    ),
                ).first()

                if existing:
                    logger.debug(f"Post already exists for {profile.name}")
                    continue

                ai_result = analyze_post(post_data["post_text"], profile.name)

                new_post = Post(
                    profile_id=profile.id,
                    post_text=post_text,
                    post_url=post_url,
                    post_hash=content_hash,
                    post_timestamp=post_data.get("post_timestamp"),
                    summary=ai_result["summary"],
                    category=ai_result["category"],
                    suggested_reply=ai_result["suggested_reply"],
                )
                db.add(new_post)
                db.commit()

                digest_entries.append({
                    "name": profile.name,
                    "category": ai_result["category"],
                    "summary": ai_result["summary"],
                    "suggested_reply": ai_result["suggested_reply"],
                    "post_url": post_data["post_url"],
                })

        profile_names = [p.name for p in profiles]
        send_digest(digest_entries, profile_names=profile_names, user_id=user_id)
        if digest_entries:
            logger.info(f"Daily digest sent with {len(digest_entries)} new posts.")
        else:
            logger.info("No new posts found today. Notification sent.")

    except Exception as e:
        logger.error(f"Error in daily job: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        run_all_users_job,
        trigger=CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="daily_linkedin_job",
        name="Daily LinkedIn Relationship Intelligence",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started. Daily job scheduled for 8:00 AM.")
