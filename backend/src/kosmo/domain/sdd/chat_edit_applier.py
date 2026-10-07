from __future__ import annotations

import re

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.domain.sdd.output_guardrails import (
    detect_feature_level_violations,
    detect_technical_terms,
)
from kosmo.domain.sdd.plan_diffs import apply_change_diff, collapse_whitespace


def apply_markdown_suggestion(
    markdown: str,
    *,
    section: str | None,
    diff_before: str,
    diff_after: str,
) -> str | None:
    """Aplica una sugerencia por fragmento sobre markdown. None si no calza."""
    return apply_change_diff(markdown, before=diff_before, after=diff_after, section=section)


def apply_feature_attribute(current: str, *, diff_before: str, diff_after: str) -> str | None:
    """Aplica una sugerencia sobre el valor de un atributo de caracteristica."""
    if not diff_before.strip():
        return diff_after if diff_after.strip() else None

    if diff_before in current:
        return current.replace(diff_before, diff_after, 1)

    if diff_after.strip() and diff_after.strip() in current and diff_before.strip() not in current:
        return current

    norm_before = collapse_whitespace(diff_before)
    if norm_before in collapse_whitespace(current):
        return _replace_normalized(current, diff_before, diff_after)

    return None


def _replace_normalized(text: str, before: str, after: str) -> str | None:
    tokens = re.split(r"(\s+)", before)
    pattern_parts = [re.escape(t) if t.strip() else r"\s+" for t in tokens]
    match = re.compile("".join(pattern_parts)).search(text)
    if match is None:
        return None
    return text[: match.start()] + after + text[match.end() :]


def check_fragment_terms(phase: SpecPhase, fragment: str) -> list[str]:
    """Terminos prohibidos de la fase presentes en el fragmento sugerido."""
    if phase == SpecPhase.DESCUBRIMIENTO:
        result = detect_technical_terms(fragment)
    elif phase == SpecPhase.CARACTERISTICAS:
        result = detect_feature_level_violations(fragment)
    else:
        return []

    return [v.term for v in result.violations]
