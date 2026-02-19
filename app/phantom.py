import os
import logging
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

PHANTOMBUSTER_API_KEY = os.environ.get("PHANTOMBUSTER_API_KEY", "")
PHANTOMBUSTER_BASE_URL = "https://api.phantombuster.com/api/v2"


def get_headers():
    return {
        "X-Phantombuster-Key": PHANTOMBUSTER_API_KEY,
        "Content-Type": "application/json",
    }


async def fetch_agent_output(agent_id: str) -> dict:
    url = f"{PHANTOMBUSTER_BASE_URL}/agents/fetch-output"
    params = {"id": agent_id}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=get_headers(), params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"PhantomBuster API error fetching agent {agent_id}: {e}")
        return {}


async def launch_agent(agent_id: str) -> dict:
    url = f"{PHANTOMBUSTER_BASE_URL}/agents/launch"
    payload = {"id": agent_id}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"PhantomBuster API error launching agent {agent_id}: {e}")
        return {}


async def get_recent_posts(agent_id: str) -> list[dict]:
    output = await fetch_agent_output(agent_id)
    if not output:
        logger.warning(f"No output from PhantomBuster agent {agent_id}")
        return []

    result_object = output.get("resultObject")
    if not result_object:
        logger.warning(f"No resultObject in PhantomBuster output for agent {agent_id}")
        return []

    posts = []
    if isinstance(result_object, list):
        items = result_object
    elif isinstance(result_object, str):
        import json
        try:
            items = json.loads(result_object)
        except json.JSONDecodeError:
            logger.error("Failed to parse resultObject as JSON")
            return []
    else:
        items = [result_object]

    cutoff = datetime.utcnow() - timedelta(hours=24)

    for item in items:
        post_text = item.get("postContent") or item.get("text") or item.get("description", "")
        post_url = item.get("postUrl") or item.get("url", "")
        timestamp_str = item.get("timestamp") or item.get("date") or item.get("publishedDate", "")

        post_time = None
        if timestamp_str:
            for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    post_time = datetime.strptime(timestamp_str, fmt)
                    break
                except ValueError:
                    continue

        if post_time and post_time < cutoff:
            continue

        if post_text:
            posts.append({
                "post_text": post_text,
                "post_url": post_url,
                "post_timestamp": post_time,
            })

    logger.info(f"Found {len(posts)} recent posts from PhantomBuster agent {agent_id}")
    return posts
