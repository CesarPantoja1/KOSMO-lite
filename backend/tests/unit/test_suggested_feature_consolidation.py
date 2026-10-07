from __future__ import annotations

import pytest


@pytest.mark.unit
def test_suggested_feature_is_canonical_and_reexported() -> None:
    from kosmo.contracts.pipeline.phase_outputs import SuggestedFeature as CanonicalSuggestedFeature
    from kosmo.contracts.sdd.document import SuggestedFeature as ReexportedSuggestedFeature

    assert CanonicalSuggestedFeature is ReexportedSuggestedFeature

    feature = CanonicalSuggestedFeature(number=1, title="Auth", description="Login flow", origin="discovery")
    assert isinstance(feature, ReexportedSuggestedFeature)
    assert feature.number == 1
    assert feature.title == "Auth"
    assert feature.description == "Login flow"
    assert feature.origin == "discovery"


@pytest.mark.unit
def test_document_module_getattr_unknown_attribute_raises() -> None:
    import kosmo.contracts.sdd.document as doc_mod

    with pytest.raises(AttributeError, match="has no attribute 'NonExistentAttribute'"):
        _ = doc_mod.NonExistentAttribute
