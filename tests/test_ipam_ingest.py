"""Pruebas unitarias para la lógica de ingesta de Redes e IPAM (Fase 2)."""

import pytest
from unittest.mock import MagicMock
from netbox_ingest.runners.ingest_ipam import (
    generate_spoke_prefixes_and_vlans,
    build_ipam_catalog,
    run_ingest,
)
from netbox_ingest.ipam_definitions import (
    IPAM_ROLES,
    VRFS,
    STANDARD_VLANS,
    HUB_SITES,
    SPOKE_SITES,
)


def test_standard_vlans_count():
    """Valida que la plantilla estándar cuente exactamente con 9 VLANs."""
    assert len(STANDARD_VLANS) == 9
    vids = [v["vid"] for v in STANDARD_VLANS]
    assert vids == [10, 11, 20, 30, 40, 50, 60, 80, 90]


def test_generate_spoke_prefixes_and_vlans():
    """Valida la generación de contenedor, VLAN group, VLANs y subredes para una sede."""
    spoke = {
        "site_name": "Delegación Alcalá De Henares",
        "site_slug": "delegacion-alcala-de-henares",
        "second_octet": 157,
    }
    container, vlans, subnets = generate_spoke_prefixes_and_vlans(spoke)

    assert container["prefix"] == "10.157.0.0/16"
    assert container["status"] == "container"
    assert container["site_slug"] == "delegacion-alcala-de-henares"

    assert len(vlans) == 9
    assert len(subnets) == 9

    # Verificar coincidencia de subredes esperadas
    expected_subnets = [
        "10.157.10.0/24",  # VLAN 10
        "10.157.11.0/24",  # VLAN 11
        "10.157.12.0/24",  # VLAN 20
        "10.157.13.0/24",  # VLAN 30
        "10.157.14.0/24",  # VLAN 40
        "10.157.15.0/24",  # VLAN 50
        "10.157.16.0/24",  # VLAN 60
        "10.157.17.0/25",  # VLAN 80
        "10.157.18.0/24",  # VLAN 90
    ]
    generated_subnets = [s["prefix"] for s in subnets]
    assert generated_subnets == expected_subnets

    # Verificar que cada subred enlace al VID correspondiente
    for s, vlan_def in zip(subnets, STANDARD_VLANS):
        assert s["vlan_vid"] == vlan_def["vid"]


def test_build_ipam_catalog():
    """Valida la compilación global del catálogo IPAM."""
    catalog = build_ipam_catalog()

    assert len(catalog["roles"]) == len(IPAM_ROLES)
    assert len(catalog["vrfs"]) == len(VRFS)
    assert len(catalog["hub_sites"]) == len(HUB_SITES)

    # VLAN groups: 2 Hubs + N Spokes
    expected_vlan_groups = len(HUB_SITES) + len(SPOKE_SITES)
    assert len(catalog["vlan_groups"]) == expected_vlan_groups

    # VLANs: 9 por cada Hub y Spoke
    expected_vlans = expected_vlan_groups * 9
    assert len(catalog["vlans"]) == expected_vlans

    # Prefijos:
    # - Global containers (4)
    # - Cloud prefixes (21)
    # - Hub containers (2) + Hub specific (4)
    # - Spoke containers (N) + Spoke subnets (N * 8)
    # - Infra transit / Overlays / VPN (12)
    assert len(catalog["prefixes"]) > 250


def test_run_ingest_mock():
    """Valida la ejecución idempotente del pipeline de ingesta con cliente simulado (Mock)."""
    mock_client = MagicMock()

    # Configurar respuestas simuladas
    mock_client.get.return_value = {"count": 0, "results": []}
    mock_client.get_all.return_value = [
        {"id": 1, "slug": "madrid-cpd", "name": "Madrid CPD"},
        {"id": 2, "slug": "jesp", "name": "JESP"},
    ]
    mock_client.post.return_value = {"id": 100}

    run_ingest(client=mock_client)

    # Verificar que se hayan realizado llamadas POST para crear objetos
    assert mock_client.post.call_count > 0
