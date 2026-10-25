"""Tests unitarios para la ingesta exclusiva de perfiles criptográficos B2B."""

from unittest.mock import MagicMock
import pytest
from netbox_ingest.runners.b2b_crypto_ingest import (
    B2BCryptoIngestRunner,
    B2B_CRYPTO_DEFINITIONS,
)


@pytest.fixture
def mock_crypto_client():
    client = MagicMock()
    # Simular que ike-prop-aes256-sha256-dh14 y ipsec-prop-aes256-sha256 ya existen de la fase anterior
    client.get_all.side_effect = lambda ep, params=None: {
        "vpn/ike-proposals": [{"id": 14, "name": "ike-prop-aes256-sha256-dh14"}],
        "vpn/ike-policies": [],
        "vpn/ipsec-proposals": [{"id": 256, "name": "ipsec-prop-aes256-sha256"}],
        "vpn/ipsec-policies": [],
        "vpn/ipsec-profiles": [],
    }.get(ep, [])

    client.post.return_value = {"id": 999}
    client.patch.return_value = {"id": 999}
    return client


def test_definitions_schema_compliance():
    """Valida los parámetros de las propuestas frente al schema de NetBox."""
    valid_enc = {"aes-256-cbc", "aes-128-cbc"}
    valid_auth = {"hmac-sha256", "hmac-sha512"}

    for prop in B2B_CRYPTO_DEFINITIONS["ike_proposals"]:
        assert prop["encryption_algorithm"] in valid_enc
        assert prop["authentication_algorithm"] in valid_auth
        assert prop["group"] in {2, 14, 19}

    for prop in B2B_CRYPTO_DEFINITIONS["ipsec_proposals"]:
        assert prop["encryption_algorithm"] in valid_enc
        assert prop["authentication_algorithm"] in valid_auth


def test_dry_run_zero_writes(mock_crypto_client):
    """Valida que en dry-run no se escribe nada en NetBox."""
    runner = B2BCryptoIngestRunner(client=mock_crypto_client, dry_run=True)
    stats = runner.run()

    mock_crypto_client.post.assert_not_called()
    mock_crypto_client.patch.assert_not_called()
    assert stats["proposals_created"] == 3  # 2 IKE (dh19, dh2) + 1 IPsec (sha512)
    assert stats["proposals_reused"] == 2   # 1 IKE (dh14) + 1 IPsec (sha256)
    assert stats["profiles_created"] == 3   # 3 perfiles B2B


def test_commit_writes_and_reuses(mock_crypto_client):
    """Valida que en commit se crean las propuestas y perfiles faltantes reutilizando las existentes."""
    runner = B2BCryptoIngestRunner(client=mock_crypto_client, dry_run=False)
    stats = runner.run()

    assert mock_crypto_client.post.call_count > 0
    assert stats["profiles_created"] == 3
    assert stats["proposals_reused"] == 2
    assert len(stats["errors"]) == 0
