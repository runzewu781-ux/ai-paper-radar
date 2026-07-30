import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def translate_title(title: str) -> str | None:
    if not settings.llm_api_key:
        logger.warning("LLM_API_KEY not set, skipping translation")
        return None

    url = f"{settings.llm_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "system",
                "content": "你是一个学术论文标题翻译器。将英文论文标题翻译成简洁准确的中文。只输出翻译结果，不要解释，不要加引号。保留专有名词（如模型名、方法名）的英文原文。",
            },
            {"role": "user", "content": title},
        ],
        "temperature": 0.3,
        "max_tokens": 200,
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("Translation failed for '%s': %s", title[:50], e)
        return None


def translate_titles_batch(titles: list[str]) -> list[str | None]:
    results = []
    for title in titles:
        results.append(translate_title(title))
    return results
