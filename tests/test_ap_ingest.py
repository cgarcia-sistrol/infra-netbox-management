import pytest
import ipaddress
from netbox_ingest.runners.ingest_access_points import MODEL_MAPPING, resolve_site_and_mask


def test_model_mapping_complete():
    """Verifica que todos los códigos de UniFi estén mapeados a modelos válidos."""
    expected_codes = ["UALR6v2", "UKPW", "U7PRO", "U7PG2", "U6M", "U7LR", "UAP6MP"]
    for code in expected_codes:
        assert code in MODEL_MAPPING, f"Falta código {code} en MODEL_MAPPING"
        spec = MODEL_MAPPING[code]
        assert "model" in spec
        assert "part_number" in spec
        assert "slug" in spec
        assert "iface_type" in spec


def test_resolve_disponible_site_jesp():
    """Verifica que los APs DISPONIBLE se asignen a JESP con status staged."""
    prefixes = [
        (ipaddress.ip_network("10.150.0.0/16"), "Default", "Test Container")
    ]
    site, mask, status = resolve_site_and_mask("DISPONIBLE-01", "10.150.17.13", prefixes)
    assert site == "JESP"
    assert mask == 25
    assert status == "staged"


def test_resolve_almeria_special_rule():
    """Verifica que ALM-01 resuelva a Delegación Almería."""
    prefixes = []
    site, mask, status = resolve_site_and_mask("ALM-01", "10.101.194.30", prefixes)
    assert site == "Delegación Almería"
    assert mask == 24
    assert status == "offline"


def test_resolve_site_longest_prefix():
    """Verifica la resolución por prefijo más específico (LPM)."""
    prefixes = [
        (ipaddress.ip_network("10.169.0.0/16"), "ArcelorMittal Veriña", "Contenedor"),
        (ipaddress.ip_network("10.169.17.0/25"), "ArcelorMittal Veriña", "Subred Gestion Infra"),
    ]
    site, mask, status = resolve_site_and_mask("ARC-GIJ-01 Sala de Control", "10.169.17.1", prefixes)
    assert site == "ArcelorMittal Veriña"
    assert mask == 25
    assert status == "active"
