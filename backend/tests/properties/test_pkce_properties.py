from __future__ import annotations

import re
import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from kosmo.domain.auth.pkce import s256_challenge, verify_s256

# Caracteres válidos para code_verifier según RFC 7636: [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
_PKCE_ALPHABET = string.ascii_letters + string.digits + "-._~"
_VALID_VERIFIER = st.text(st.sampled_from(_PKCE_ALPHABET), min_size=43, max_size=128)


@pytest.mark.property
@settings(max_examples=60)
@given(_VALID_VERIFIER)
def test_pkce_roundtrip_identity(verifier: str) -> None:
    """Propiedad: todo code_verifier válido genera un challenge que verifica exitosamente consigo mismo."""
    challenge = s256_challenge(verifier)
    assert verify_s256(verifier, challenge) is True


@pytest.mark.property
@settings(max_examples=50)
@given(_VALID_VERIFIER)
def test_pkce_challenge_format_invariants(verifier: str) -> None:
    """Propiedad: el challenge S256 tiene siempre exactamente 43 caracteres url-safe sin padding '='."""
    challenge = s256_challenge(verifier)

    # SHA-256 produce 32 bytes -> 44 chars en base64 con 1 '=' -> 43 chars sin '='
    assert len(challenge) == 43
    assert "=" not in challenge
    assert bool(re.match(r"^[A-Za-z0-9_-]{43}$", challenge))


@pytest.mark.property
@settings(max_examples=50)
@given(_VALID_VERIFIER, st.integers(min_value=0, max_value=42))
def test_pkce_tampered_challenge_always_fails(verifier: str, index: int) -> None:
    """Propiedad: cualquier alteración de un solo caracter en el challenge invalida la verificación."""
    challenge = s256_challenge(verifier)
    original_char = challenge[index]
    tampered_char = "b" if original_char != "b" else "c"
    tampered_challenge = challenge[:index] + tampered_char + challenge[index + 1 :]

    assert verify_s256(verifier, tampered_challenge) is False


@pytest.mark.property
@settings(max_examples=50)
@given(_VALID_VERIFIER, _VALID_VERIFIER)
def test_pkce_collision_resistance_for_distinct_verifiers(v1: str, v2: str) -> None:
    """Propiedad: dos verifiers distintos deben generar challenges distintos."""
    if v1 != v2:
        c1 = s256_challenge(v1)
        c2 = s256_challenge(v2)
        assert c1 != c2
        assert verify_s256(v1, c2) is False
        assert verify_s256(v2, c1) is False
