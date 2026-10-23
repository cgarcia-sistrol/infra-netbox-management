import pytest
from netbox_ingest.runners.ingest_wireless_lans import (
    WIRELESS_LAN_GROUPS,
    WIRELESS_LANS,
    get_wifi_interface_type,
    resolve_ssids_for_mac,
)


def test_wireless_groups_definition():
    """Verifica que los tres grupos de Wireless LAN estén definidos."""
    expected_slugs = ["corporativo", "invitados", "ot-servicios"]
    for slug in expected_slugs:
        assert slug in WIRELESS_LAN_GROUPS
        assert "name" in WIRELESS_LAN_GROUPS[slug]


def test_wireless_lans_definition():
    """Verifica que los 8 SSIDs estén definidos con auth y cifrado correctos."""
    assert len(WIRELESS_LANS) == 8
    edison_corp = next(w for w in WIRELESS_LANS if w["ssid"] == "EDISON_NEXT")
    assert edison_corp["auth_type"] == "wpa-personal"
    assert edison_corp["auth_cipher"] == "aes"
    assert edison_corp["group_slug"] == "corporativo"

    edison_eap = next(w for w in WIRELESS_LANS if w["ssid"] == "EDISON_NEXT_")
    assert edison_eap["auth_type"] == "wpa-enterprise"
    assert edison_eap["group_slug"] == "corporativo"

    guest = next(w for w in WIRELESS_LANS if w["ssid"] == "INVITADOS_EDISON_NEXT")
    assert guest["group_slug"] == "invitados"


def test_wifi_interface_type():
    """Verifica el estándar 802.11 asignado a cada modelo."""
    assert get_wifi_interface_type("U7PRO") == "ieee802.11be"
    assert get_wifi_interface_type("UKPW") == "ieee802.11be"
    assert get_wifi_interface_type("UALR6v2") == "ieee802.11ax"
    assert get_wifi_interface_type("U6M") == "ieee802.11ax"
    assert get_wifi_interface_type("UAP6MP") == "ieee802.11ax"
    assert get_wifi_interface_type("U7PG2") == "ieee802.11ac"
    assert get_wifi_interface_type("U7LR") == "ieee802.11ac"


def test_resolve_ssids_for_mac():
    """Verifica la resolución de SSIDs para un AP dado su MAC y grupos."""
    ap_groups = [
        {"id": "grp1", "name": "BNC-ZNF", "device_macs": ["0c:ea:14:bc:8e:dc"]},
        {"id": "grp2", "name": "All APs", "device_macs": ["0c:ea:14:bc:8e:dc"]},
    ]
    wlans = [
        {"name": "EDISON_NEXT", "ap_group_ids": ["grp1"]},
        {"name": "INVITADOS_EDISON_NEXT", "ap_group_ids": ["grp1"]},
        {"name": "EDISON_NEXT_", "ap_group_ids": ["other"]},
    ]
    ssids = resolve_ssids_for_mac("0C:EA:14:BC:8E:DC", ap_groups, wlans)
    assert "EDISON_NEXT" in ssids
    assert "INVITADOS_EDISON_NEXT" in ssids
    assert "EDISON_NEXT_" not in ssids
