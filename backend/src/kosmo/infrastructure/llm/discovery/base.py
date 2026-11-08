from __future__ import annotations

import re


def is_excluded_model(model_id: str) -> bool:
    """Filtra modelos no aptos (embeddings, audio, etc.), snapshots fechados o series obsoletas."""
    mid = model_id.lower()
    if bool(re.search(r"-\d{8}$", mid)):
        return True
    if any(mid.startswith(prefix) for prefix in ("o1", "o3", "o4")):
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
