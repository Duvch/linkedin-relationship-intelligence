import os
import logging
import httpx

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


async def send_digest(entries: list[dict]) -> bool:
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL is not set. Skipping Slack notification.")
        return False

    if not entries:
        logger.info("No entries to send to Slack.")
        return True

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "\U0001f4c5 Daily Relationship Update",
            },
        },
        {"type": "divider"},
    ]

    for entry in entries:
        text = (
            f"*Name:* {entry.get('name', 'Unknown')}\n"
            f"*Category:* {entry.get('category', 'Other')}\n"
            f"*Summary:* {entry.get('summary', 'N/A')}\n"
            f"*Suggested Reply:* {entry.get('suggested_reply', 'N/A')}\n"
            f"*Post Link:* {entry.get('post_url', 'N/A')}"
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        })
        blocks.append({"type": "divider"})

    payload = {"blocks": blocks}

    try:
        async with httpx.AsyncClient(timeout=15) as http_client:
            response = await http_client.post(SLACK_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            logger.info(f"Slack digest sent successfully with {len(entries)} entries.")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Slack digest: {e}")
        return False
