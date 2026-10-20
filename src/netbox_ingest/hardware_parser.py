"""Parser y validador del catálogo de hardware para ingesta en NetBox."""

from typing import Any, Dict, List, Tuple
from netbox_ingest.hardware_definitions import (
    MANUFACTURERS,
    DEVICE_ROLES,
    PLATFORMS,
    DEVICE_TYPES,
)


def validate_hardware_catalog() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Valida la integridad referencial y estructural del catálogo de hardware."""
    mfg_slugs = {m["slug"] for m in MANUFACTURERS}
    role_slugs = {r["slug"] for r in DEVICE_ROLES}
    platform_slugs = {p["slug"] for p in PLATFORMS}

    # Validar plataformas
    for p in PLATFORMS:
        if p["manufacturer_slug"] not in mfg_slugs:
            raise ValueError(f"Fabricante '{p['manufacturer_slug']}' en plataforma '{p['name']}' no existe.")

    # Validar tipos de dispositivo
    for dt in DEVICE_TYPES:
        if dt["manufacturer_slug"] not in mfg_slugs:
            raise ValueError(f"Fabricante '{dt['manufacturer_slug']}' en modelo '{dt['model']}' no existe.")
        if dt.get("role_slug") and dt["role_slug"] not in role_slugs:
            raise ValueError(f"Rol '{dt['role_slug']}' en modelo '{dt['model']}' no existe.")
        if dt.get("platform_slug") and dt["platform_slug"] not in platform_slugs:
            raise ValueError(f"Plataforma '{dt['platform_slug']}' en modelo '{dt['model']}' no existe.")
        if not dt.get("slug"):
            raise ValueError(f"Modelo '{dt['model']}' no tiene slug asignado.")

    return MANUFACTURERS, DEVICE_ROLES, PLATFORMS, DEVICE_TYPES


def get_catalog_summary() -> Dict[str, Any]:
    """Devuelve un resumen cuantificado del catálogo de hardware."""
    mfgs, roles, platforms, device_types = validate_hardware_catalog()

    total_interfaces = sum(len(dt.get("interfaces", [])) for dt in device_types)
    total_console_ports = sum(len(dt.get("console_ports", [])) for dt in device_types)
    total_power_ports = sum(len(dt.get("power_ports", [])) for dt in device_types)

    by_mfg: Dict[str, int] = {}
    for dt in device_types:
        mfg = dt["manufacturer_slug"]
        by_mfg[mfg] = by_mfg.get(mfg, 0) + 1

    return {
        "manufacturers_count": len(mfgs),
        "roles_count": len(roles),
        "platforms_count": len(platforms),
        "device_types_count": len(device_types),
        "total_interfaces": total_interfaces,
        "total_console_ports": total_console_ports,
        "total_power_ports": total_power_ports,
        "models_by_manufacturer": by_mfg,
    }
