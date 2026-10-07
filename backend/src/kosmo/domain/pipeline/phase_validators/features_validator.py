from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any, cast

from kosmo.contracts.pipeline.phase_outputs import ValidationResult
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.guardrails import DISCOVERY_SECTIONS
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.domain.codegen.integration_rules import detect_capability_overlap
from kosmo.domain.sdd.output_guardrails import (
    detect_feature_level_violations,
    detect_technical_terms,
)


def _normalize_text(text: str) -> set[str]:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()
    stopwords = {
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
        "y",
        "o",
        "e",
        "u",
        "en",
        "para",
        "por",
        "con",
        "sin",
        "sobre",
        "tras",
        "desde",
        "hasta",
        "que",
        "es",
        "son",
        "este",
        "esta",
        "estos",
        "estas",
        "como",
        "quiero",
        "sistema",
        "usuario",
        "permite",
        "debe",
        "poder",
        "funcionalidad",
        "caracteristica",
        "proyecto",
    }
    return {w for w in words if len(w) > 2 and w not in stopwords}


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a.intersection(set_b)) / len(set_a.union(set_b))


def _count_words(text: str) -> int:
    return len(text.strip().split())


def _mentions_discovery_section(origin: str) -> bool:
    return any(section.lower() in origin.lower() for section in DISCOVERY_SECTIONS)


_REQUIRED_FIELDS = ["number", "title", "description", "origin"]

MAX_TITLE_WORDS = 6
MIN_TITLE_CHARS = 3
MIN_DESC_CHARS = 20
MIN_ORIGIN_CHARS = 15


def validate_feature_structure(features: Any) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(features, list):
        return ValidationResult(
            is_valid=False,
            errors=["Las características deben presentarse en una lista."],
        )

    if not features:
        return ValidationResult(
            is_valid=False,
            errors=["La lista de características está vacía."],
        )

    for idx, raw_feat in enumerate(cast(list[object], features)):
        if not isinstance(raw_feat, dict):
            errors.append(f"El elemento en el índice {idx} no es un objeto válido.")
            continue

        feat: dict[str, Any] = {}
        for k, v in cast(dict[object, object], raw_feat).items():
            if isinstance(k, str):
                feat[k] = v

        title = str(feat.get("title", f"Característica {idx + 1}"))

        for field in _REQUIRED_FIELDS:
            if field not in feat:
                errors.append(f"Característica '{title}' (índice {idx}) no tiene el campo requerido '{field}'.")

        if any(f not in feat for f in _REQUIRED_FIELDS):
            continue

        number = feat["number"]
        title_val = feat["title"]
        desc_val = feat["description"]
        origin_val = feat["origin"]

        if not isinstance(number, int):
            errors.append(f"El campo 'number' en la característica '{title}' debe ser un número entero.")

        if not isinstance(title_val, str) or not title_val.strip():
            errors.append(f"El campo 'title' en la característica {idx + 1} debe ser un texto no vacío.")
        else:
            if len(title_val.strip()) < MIN_TITLE_CHARS:
                errors.append(f"El título '{title_val}' es demasiado corto (mínimo {MIN_TITLE_CHARS} caracteres).")
            word_count = _count_words(title_val)
            if word_count > MAX_TITLE_WORDS:
                errors.append(
                    f"El título '{title_val}' tiene {word_count} palabras; el máximo es {MAX_TITLE_WORDS} palabras."
                )

        if not isinstance(desc_val, str) or not desc_val.strip():
            errors.append(f"La descripción en la característica '{title}' debe ser un texto no vacío.")
        elif len(desc_val.strip()) < MIN_DESC_CHARS:
            errors.append(f"La descripción de '{title}' es demasiado corta (mínimo {MIN_DESC_CHARS} caracteres).")

        if not isinstance(origin_val, str) or not origin_val.strip():
            errors.append(f"El campo 'origin' en la característica '{title}' debe ser un texto no vacío.")
        else:
            if len(origin_val.strip()) < MIN_ORIGIN_CHARS:
                errors.append(f"El origen de '{title}' es demasiado corto (mínimo {MIN_ORIGIN_CHARS} caracteres).")
            if not _mentions_discovery_section(origin_val):
                errors.append(
                    f"El origen de '{title}' no menciona ninguna sección del descubrimiento; "
                    f"debe incluir trazabilidad hacia al menos una de: {', '.join(DISCOVERY_SECTIONS)}."
                )

        for field_name, field_val in [("title", title_val), ("description", desc_val)]:
            if isinstance(field_val, str):
                result = detect_feature_level_violations(field_val, section=f"característica '{title}' ({field_name})")
                if not result.is_valid:
                    for violation in result.violations:
                        errors.append(
                            f"Término prohibido '{violation.term}' encontrado en "
                            f"{violation.section}: {violation.context}"
                        )

        if isinstance(origin_val, str):
            tech_result = detect_technical_terms(origin_val, section=f"característica '{title}' (origin)")
            if not tech_result.is_valid:
                for violation in tech_result.violations:
                    errors.append(
                        f"Término técnico prohibido '{violation.term}' encontrado en "
                        f"{violation.section}: {violation.context}"
                    )

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def validate_feature_uniqueness(
    features: Any,
    existing_titles: list[str] | None = None,
    existing_features: Sequence[Feature] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(features, list) or not features:
        return ValidationResult(is_valid=True)

    normalized_titles: list[tuple[str, set[str]]] = []
    normalized_descs: list[tuple[str, set[str]]] = []
    feature_objects: list[Feature] = []

    for idx, raw_feat in enumerate(cast(list[object], features)):
        if isinstance(raw_feat, dict):
            feat: dict[str, Any] = {}
            for k, v in cast(dict[object, object], raw_feat).items():
                if isinstance(k, str):
                    feat[k] = v

            title = feat.get("title")
            desc = feat.get("description")
            origin = str(feat.get("origin", ""))
            num = feat.get("number", idx + 1)
            if isinstance(title, str) and isinstance(desc, str):
                normalized_titles.append((title, _normalize_text(title)))
                normalized_descs.append((title, _normalize_text(desc)))
                feature_objects.append(
                    Feature(
                        id=FeatureId(f"feat_{idx}"),
                        project_id=ProjectId("temp"),
                        number=int(num) if isinstance(num, int) else idx + 1,
                        title=title,
                        slug=f"feature-{idx + 1}",
                        description=desc,
                        origin=origin,
                    )
                )

    n = len(normalized_titles)
    for i in range(n):
        title_i, title_words_i = normalized_titles[i]
        _, desc_words_i = normalized_descs[i]

        for j in range(i + 1, n):
            title_j, title_words_j = normalized_titles[j]
            _, desc_words_j = normalized_descs[j]

            title_sim = _jaccard_similarity(title_words_i, title_words_j)
            if title_sim > 0.4:
                errors.append(
                    f"Redundancia semántica detectada: los títulos de '{title_i}' y "
                    f"'{title_j}' son demasiado similares (similitud {title_sim:.2f})."
                )

            desc_sim = _jaccard_similarity(desc_words_i, desc_words_j)
            if desc_sim > 0.5:
                errors.append(
                    f"Redundancia semántica detectada: las descripciones de '{title_i}' "
                    f"y '{title_j}' son demasiado similares (similitud {desc_sim:.2f})."
                )

    seen_warnings: set[str] = set()
    for feat_i in feature_objects:
        other_feats = [f for f in feature_objects if f.id != feat_i.id]
        overlaps = detect_capability_overlap(feat_i, other_feats)
        for overlap in overlaps:
            if overlap.message and overlap.message not in seen_warnings:
                seen_warnings.add(overlap.message)
                warnings.append(overlap.message)

    if existing_features:
        for feat_obj in feature_objects:
            overlaps = detect_capability_overlap(feat_obj, existing_features)
            for overlap in overlaps:
                if overlap.message and overlap.message not in seen_warnings:
                    seen_warnings.add(overlap.message)
                    warnings.append(overlap.message)

    if existing_titles:
        normalized_existing = [(t, _normalize_text(t)) for t in existing_titles]
        for title_gen, gen_words in normalized_titles:
            for title_exist, exist_words in normalized_existing:
                sim = _jaccard_similarity(gen_words, exist_words)
                if sim > 0.4:
                    errors.append(
                        f"Redundancia semántica detectada: la característica generada "
                        f"'{title_gen}' ya existe o es muy similar a la característica "
                        f"existente '{title_exist}' (similitud {sim:.2f})."
                    )

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
