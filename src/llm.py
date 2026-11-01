import time
from functools import lru_cache

from google import genai
from google.genai import types

from . import config


@lru_cache(maxsize=1)
def client():
    return genai.Client(api_key=config.get("GEMINI_API_KEY"), http_options=types.HttpOptions(timeout=45_000))


def _retry(fn, tries=3):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def generate(contents, cfg):
    return _retry(lambda: client().models.generate_content(model=config.GEMINI_MODEL, contents=contents, config=cfg))


def embed(text: str) -> list[float]:
    r = _retry(
        lambda: client().models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=768, task_type="SEMANTIC_SIMILARITY"),
        )
    )
    return list(r.embeddings[0].values)


def draft_reply(ref: str, summary: str, department: str, sla_hours: int, language: str) -> str:
    lang = "Tamil" if language == "ta" else "English"
    prompt = (
        f"Write a short, polite reply (3-4 sentences, in {lang}) from the Greater Chennai Corporation grievance cell "
        f"to a citizen. Complaint reference: {ref}. Issue: {summary}. It has been registered and forwarded to "
        f"{department}, with a target resolution time of {sla_hours} hours. Do not promise anything beyond that. "
        "Output only the message text."
    )
    r = generate(prompt, types.GenerateContentConfig(temperature=0.3))
    return (r.text or "").strip()
