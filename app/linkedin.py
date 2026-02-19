import os
import re
import logging
import time
from datetime import datetime
import requests

logger = logging.getLogger(__name__)

RAPIDAPI_HOST = "fresh-linkedin-scraper-api.p.rapidapi.com"
RAPIDAPI_BASE = f"https://{RAPIDAPI_HOST}"


def _get_api_key():
    key = os.environ.get("RAPIDAPI_KEY", "")
    if not key:
        logger.warning("RAPIDAPI_KEY not configured.")
    return key


def extract_username(linkedin_url: str) -> str:
    match = re.search(r"linkedin\.com/in/([^/?#]+)", linkedin_url)
    if match:
        return match.group(1).strip("/")
    match = re.search(r"linkedin\.com/company/([^/?#]+)", linkedin_url)
    if match:
        return match.group(1).strip("/")
    return ""


def _get_headers():
    return {
        "x-rapidapi-key": _get_api_key(),
        "x-rapidapi-host": RAPIDAPI_HOST,
    }


def _get_user_urn(username: str) -> str:
    url = f"{RAPIDAPI_BASE}/api/v1/user/profile"
    try:
        resp = requests.get(url, headers=_get_headers(), params={"username": username}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and isinstance(data.get("data"), dict):
            urn = data["data"].get("urn", "")
            if urn:
                logger.info(f"Got URN for {username}: {urn}")
                return urn
        logger.warning(f"No URN found for {username}")
        return ""
    except Exception as e:
        logger.error(f"Failed to get profile/URN for {username}: {e}")
        return ""


async def get_recent_posts(linkedin_url: str) -> list[dict]:
    username = extract_username(linkedin_url)
    if not username:
        logger.warning(f"Could not extract username from URL: {linkedin_url}")
        return []

    api_key = _get_api_key()
    if not api_key:
        return []

    urn = _get_user_urn(username)
    if not urn:
        return []

    time.sleep(1)

    try:
        url = f"{RAPIDAPI_BASE}/api/v1/user/posts"
        logger.info(f"Fetching posts for {username}...")
        resp = requests.get(url, headers=_get_headers(), params={"urn": urn, "page": "1"}, timeout=30)

        if resp.status_code == 429:
            logger.warning("Rate limited by API. Try again later.")
            return []

        resp.raise_for_status()
        raw = resp.json()

        if not raw.get("success"):
            logger.warning(f"API returned unsuccessful response for {username}: {raw.get('message', '')}")
            return []

        raw_posts = raw.get("data", [])
        if not isinstance(raw_posts, list):
            raw_posts = []

        if not raw_posts:
            logger.info(f"No posts found for {username}")
            return []

        posts = []
        for item in raw_posts:
            if not isinstance(item, dict):
                continue

            post_text = item.get("text", "")
            if not post_text:
                continue

            post_id = item.get("id", "")
            post_url = ""
            if post_id:
                post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{post_id}/"

            author_data = item.get("author", {})
            if isinstance(author_data, dict):
                author_url = author_data.get("url", "")

            post_time = None
            created = item.get("created", {})
            if isinstance(created, dict):
                created_date = created.get("date", "") or created.get("time", "")
                if created_date:
                    if isinstance(created_date, (int, float)):
                        try:
                            if created_date > 1e12:
                                post_time = datetime.utcfromtimestamp(created_date / 1000)
                            else:
                                post_time = datetime.utcfromtimestamp(created_date)
                        except (ValueError, OSError):
                            pass
                    elif isinstance(created_date, str):
                        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                            try:
                                post_time = datetime.strptime(created_date.split(".")[0].split("Z")[0], fmt)
                                break
                            except ValueError:
                                continue

            posts.append({
                "post_text": post_text,
                "post_url": post_url,
                "post_timestamp": post_time,
            })

        logger.info(f"Found {len(posts)} posts for {username}")
        return posts

    except Exception as e:
        logger.error(f"Error fetching posts for {username}: {e}", exc_info=True)
        return []


def reset_linkedin_client():
    pass
