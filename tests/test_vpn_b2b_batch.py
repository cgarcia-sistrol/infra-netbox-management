"""Tests unitarios para el runner de ingesta de túneles VPN B2B (Opción A)."""

import pytest
from unittest.mock import MagicMock
from netbox_ingest.runners.vpn_b2b_batch_runner import (
    B2BVPNBatchRunner,
    determine_crypto_profile,
    extract_tenant_name,
    slugify,
    CRYPTO_PROFILES,
    CUSTOM_FIELDS_B2B,
)


def test_slugify():
    assert slugify("to-Pascual-Gurb") == "to-pascual-gurb"
    assert slugify("Cliente Ejemplo / Especial") == "cliente-ejemplo-especial"


def test_determine_crypto_profile():
    assert determine_crypto_profile("to-Axpo") == CRYPTO_PROFILES["axpo"]
    assert determine_crypto_profile("to-Pascual-Gurb") == CRYPTO_PROFILES["legacy"]
    assert determine_crypto_profile("to-Moeve") == CRYPTO_PROFILES["standard"]
    assert determine_crypto_profile("to-Orange") == CRYPTO_PROFILES["standard"]


def test_extract_tenant_name():
    assert extract_tenant_name("to-Axpo") == "Axpo"
    assert extract_tenant_name("to-Pascual-Gurb") == "Pascual Gurb"
    assert extract_tenant_name("to-Moeve") == "Moeve"
    assert extract_tenant_name("Custom-Client") == "Custom Client"


def test_custom_fields_b2b_definitions():
    names = [cf["name"] for cf in CUSTOM_FIELDS_B2B]
    assert "local_prefixes" in names
    assert "remote_prefixes" in names
    for cf in CUSTOM_FIELDS_B2B:
        assert cf["type"] == "multiobject"
        assert cf["object_types"] == ["vpn.tunnel"]
        assert cf["related_object_type"] == "ipam.prefix"


def test_runner_dry_run_option_a():
    mock_client = MagicMock()
    mock_client.get.side_effect = lambda endpoint, params=None: {
        "vpn/tunnel-groups": {"results": [{"id": 5}]},
        "extras/custom-fields": {"results": []},
        "extras/tags": {"results": []},
        "vpn/ipsec-profiles": {
            "results": [
                {"id": 7, "name": "ipsec-prof-b2b-standard-dh14"},
                {"id": 8, "name": "ipsec-prof-b2b-axpo-dh19"},
                {"id": 9, "name": "ipsec-prof-b2b-legacy-dh2"},
            ]
        },
        "tenancy/tenants": {"results": []},
        "ipam/prefixes": {"results": []},
        "dcim/interfaces": {"results": []},
        "vpn/tunnels": {"results": []},
        "vpn/tunnel-terminations": {"results": []},
    }.get(endpoint, {"results": []})

    runner = B2BVPNBatchRunner(client=mock_client, dry_run=True)
    summary = runner.run()

    # En dry-run no debe haber llamadas POST o PATCH
    assert mock_client.post.call_count == 0
    assert mock_client.patch.call_count == 0
    assert summary["errors"] == []
    assert summary["custom_fields_ensured"] == 2
    assert summary["tunnels_created"] == 15
    assert summary["terminations_created"] == 15
    assert summary["prefixes_ensured"] > 0
