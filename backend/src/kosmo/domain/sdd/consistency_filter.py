from __future__ import annotations

import re

from kosmo.contracts.ai.chat import AppliedChange
from kosmo.contracts.pipeline.consistency_phase_context import DownstreamArtifact

_STOPWORDS = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "de",
        "del",
        "al",
        "a",
        "en",
        "con",
        "por",
        "para",
        "que",
        "se",
        "su",
        "sus",
        "es",
        "son",
        "no",
        "lo",
        "como",
        "cuando",
        "donde",
        "ya",
        "más",
        "menos",
        "desde",
        "hasta",
        "entre",
        "sobre",
        "sin",
        "también",
        "cada",
        "todo",
        "todos",
        "esta",
        "este",
        "esto",
        "ser",
        "fue",
        "han",
        "ha",
        "le",
        "les",
        "ni",
        "o",
        "y",
        "pero",
    }
)

_TOKEN_RE = re.compile(r"[a-záéíóúñü]+")


def extract_key_terms(changes: list[AppliedChange]) -> set[str]:
    terms: set[str] = set()
    for change in changes:
        # Combinar descripción, texto previo y texto posterior
        text = " ".join((change.description, change.diff.before, change.diff.after))
        for token in _TOKEN_RE.findall(text.lower()):
            if len(token) >= 2 and token not in _STOPWORDS:
                terms.add(token)
    return terms


def filter_downstream_artifacts(
    artifacts: list[DownstreamArtifact],
    changes: list[AppliedChange],
) -> list[DownstreamArtifact]:
    """Prefiltra artefactos por términos del cambio; si ninguno coincide, devuelve todos."""
    terms = extract_key_terms(changes)
    if not terms:
        return artifacts

    candidates = [
        artifact
        for artifact in artifacts
        if any(term in f"{artifact.title} {artifact.description}".lower() for term in terms)
    ]
    return candidates if candidates else artifacts
