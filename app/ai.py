import os
import json
import logging
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
    base_url=AI_INTEGRATIONS_OPENAI_BASE_URL,
)


def is_rate_limit_error(exception: BaseException) -> bool:
    error_msg = str(exception)
    return (
        "429" in error_msg
        or "RATELIMIT_EXCEEDED" in error_msg
        or "quota" in error_msg.lower()
        or "rate limit" in error_msg.lower()
        or (hasattr(exception, "status_code") and exception.status_code == 429)
    )


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True,
)
def analyze_post(post_text: str, author_name: str) -> dict:
    # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
    # do not change this unless explicitly requested by the user
    prompt = f"""Analyze the following LinkedIn post by {author_name}.

Post: {post_text}

Respond in JSON with these fields:
- "summary": A single-sentence summary of the post.
- "category": Classify as one of: "Funding", "Hiring", "Launch", "Other".
- "suggested_reply": A short, professional congratulatory reply (1-2 sentences).

Return only valid JSON, no markdown."""

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a LinkedIn relationship intelligence assistant. Always respond with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=512,
        )

        content = response.choices[0].message.content or "{}"
        result = json.loads(content)

        return {
            "summary": result.get("summary", "No summary available."),
            "category": result.get("category", "Other"),
            "suggested_reply": result.get("suggested_reply", "Congratulations on the update!"),
        }
    except json.JSONDecodeError:
        logger.error(f"Failed to parse AI response as JSON for post by {author_name}")
        return {
            "summary": "Could not generate summary.",
            "category": "Other",
            "suggested_reply": "Congratulations on the update!",
        }
    except Exception as e:
        logger.error(f"OpenAI API error analyzing post by {author_name}: {e}")
        raise
