from __future__ import annotations

import pytest

import kosmo.contracts as contracts


@pytest.mark.unit
def test_contracts_init_exports_all_declared_symbols() -> None:
    # Arrange & Act
    exported_names = contracts.__all__

    # Assert: Each symbol in __all__ must exist as an attribute on the module
    for name in exported_names:
        assert hasattr(contracts, name), f"Symbol '{name}' listed in __all__ is missing on kosmo.contracts"
        attr = getattr(contracts, name)
        assert attr is not None or name in ("get_telemetry_provider",), f"Symbol '{name}' resolved to None"
