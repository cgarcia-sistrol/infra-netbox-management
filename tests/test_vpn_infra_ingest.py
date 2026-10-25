"""Tests unitarios para el runner de ingesta de túneles VPN de infraestructura."""

from unittest.mock import MagicMock
import pytest
from netbox_ingest.runners.vpn_infra_ingest import (
    VPNInfraIngestRunner,
    B2B_EXCLUSION_NAMES,
    TUNNEL_GROUPS,
    CRYPTO_DEFINITIONS,
    VPN_TAGS,
)


@pytest.fixture
def mock_netbox_client():
    client = MagicMock()
    # Mock tags
    client.get_all.side_effect = lambda ep, params=None: {
        "extras/tags": [{"id": 1, "slug": "vpn-inter-hub", "name": "vpn:inter-hub"}],
        "vpn/tunnel-groups": [{"id": 10, "slug": "inter-hub-transit", "name": "Inter-Hub Transit"}],
        "vpn/ike-proposals": [],
        "vpn/ike-policies": [],
        "vpn/ipsec-proposals": [],
        "vpn/ipsec-policies": [],
        "vpn/ipsec-profiles": [],
        "dcim/interfaces": [
            {"id": 101, "name": "to-Hub02"},
            {"id": 102, "name": "to-Hub00"},
            {"id": 103, "name": "to-Azure-01"},
            {"id": 104, "name": "to-Azure-02"},
            {"id": 105, "name": "to-Aws-01"},
            {"id": 106, "name": "to-Aws-02"},
            {"id": 107, "name": "HubVPN"},
            {"id": 108, "name": "To_Client_SPG"},
            {"id": 109, "name": "VPNClient"},
            {"id": 110, "name": "VPNCExt"},
            {"id": 111, "name": "VPNClient_LDAP"},
        ],
    }.get(ep, [])

    client.get.return_value = {"results": []}
    client.post.return_value = {"id": 200}
    client.patch.return_value = {"id": 200}
    return client


def test_crypto_definitions_integrity():
    """Comprueba que las propuestas criptográficas contienen algoritmos compatibles con NetBox."""
    valid_enc = {"aes-256-cbc", "aes-128-cbc", "aes-256-gcm", "aes-128-gcm"}
    valid_auth = {"hmac-sha256", "hmac-sha1", "hmac-sha384", "hmac-sha512"}

    for prop in CRYPTO_DEFINITIONS["ike_proposals"]:
        assert prop["encryption_algorithm"] in valid_enc
        assert prop["authentication_algorithm"] in valid_auth
        assert prop["group"] in {2, 14, 20, 21}

    for prop in CRYPTO_DEFINITIONS["ipsec_proposals"]:
        assert prop["encryption_algorithm"] in valid_enc
        assert prop["authentication_algorithm"] in valid_auth


def test_b2b_exclusion_set():
    """Verifica que los túneles de clientes y terceros están correctamente catalogados para exclusión."""
    expected_b2b = {"to-Moeve", "to-Axpo", "to-PCA", "to-Orange", "to-LNC"}
    assert expected_b2b.issubset(B2B_EXCLUSION_NAMES)


def test_dry_run_mode_zero_writes(mock_netbox_client):
    """Verifica que en modo dry-run nunca se invoca POST ni PATCH en NetBox."""
    runner = VPNInfraIngestRunner(client=mock_netbox_client, dry_run=True)
    stats = runner.run()

    mock_netbox_client.post.assert_not_called()
    mock_netbox_client.patch.assert_not_called()
    assert stats["tunnels_created"] > 0
    assert stats["skipped_b2b"] > 0
    assert len(stats["errors"]) == 0


def test_commit_mode_execution(mock_netbox_client):
    """Verifica que en modo commit se realizan llamadas de creación en NetBox."""
    runner = VPNInfraIngestRunner(client=mock_netbox_client, dry_run=False)
    stats = runner.run()

    assert mock_netbox_client.post.call_count > 0
    assert stats["tunnels_created"] == 18  # 1 interhub + 8 cloud + 2 sdwan + 7 remote access
    assert len(stats["errors"]) == 0
