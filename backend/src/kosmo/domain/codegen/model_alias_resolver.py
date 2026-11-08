from __future__ import annotations

import re


class OpenCodeModelAliasResolver:
    """Normaliza identificadores de modelos de proveedores al formato canónico esperado por OpenCode."""

    # Sufijos de fecha típicos: -YYYYMMDD o -YYYY-MM-DD
    _DATE_SUFFIX_PATTERN = re.compile(r"[-_](202\d{5}|202\d-\d{2}-\d{2})$")

    _KNOWN_ALIASES: dict[str, dict[str, str]] = {
        "anthropic": {
            "claude-3-7-sonnet-20250219": "claude-3-7-sonnet",
            "claude-3-5-sonnet-20241022": "claude-3-5-sonnet",
            "claude-3-5-sonnet-20240620": "claude-3-5-sonnet",
            "claude-3-5-haiku-20241022": "claude-3-5-haiku",
            "claude-3-opus-20240229": "claude-3-opus",
            "claude-3-sonnet-20240229": "claude-3-sonnet",
            "claude-3-haiku-20240307": "claude-3-haiku",
        },
        "openai": {
            "gpt-4o-2024-08-06": "gpt-4o",
            "gpt-4o-2024-05-13": "gpt-4o",
            "gpt-4o-mini-2024-07-18": "gpt-4o-mini",
        },
    }

    def resolve(self, provider: str, model_id: str) -> str:
        prov = provider.lower()
        cleaned = model_id.strip()

        # Google Gemini remueve el prefijo models/
        if prov in ("google", "gemini") and cleaned.startswith("models/"):
            cleaned = cleaned.removeprefix("models/")

        # Verificar alias explícito conocido
        if prov in self._KNOWN_ALIASES and cleaned in self._KNOWN_ALIASES[prov]:
            return self._KNOWN_ALIASES[prov][cleaned]

        # Quitar sufijo de fecha si no coincide con un alias explícito
        stripped = self._DATE_SUFFIX_PATTERN.sub("", cleaned)
        return stripped if stripped else cleaned
