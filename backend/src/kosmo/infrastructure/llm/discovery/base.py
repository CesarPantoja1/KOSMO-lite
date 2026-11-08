from __future__ import annotations

import re


def is_excluded_model(model_id: str) -> bool:
    """Filtra modelos que no son de tipo chat / conversational reasoning o snapshots fechados redundantes."""
    mid = model_id.lower()
    if bool(re.search(r"-\d{8}$", mid)):
        return True
    excluded_keywords = (
        "embed",
        "embedding",
        "whisper",
        "tts",
        "audio",
        "realtime",
        "moderation",
        "dall-e",
        "davinci",
        "babbage",
        "curie",
        "ada",
        "instruct",
        "similarity",
        "search",
    )
    return any(kw in mid for kw in excluded_keywords)
