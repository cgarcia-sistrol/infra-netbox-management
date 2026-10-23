"""Módulo de parsing y normalización de ubicaciones desde Freshservice a NetBox."""

import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

EXCLUDED_LOCATION_IDS = {
    53000219526,  # Oficina Madrid - Dr Esquerdo
    53000219543,  # Oficina Madrid - Velázquez
    53000219539,  # Oficina Barcelona - Central
    53000219549,  # Tesiin
}

AGENCY_REGION_MAPPING = {
    53000219551: ("Central", "central", "Sedes adscritas a Central Agency"),
    53000219524: ("B2B Northeast", "b2b-northeast", "Plantas industriales Nordeste"),
    53000219536: ("B2G Northeast", "b2g-northeast", "Delegaciones y contratos públicos Nordeste"),
    53000219527: ("Levante", "levante", "Plantas y delegaciones Comunidad Valenciana, Murcia, Albacete"),
    53000219530: ("Mid North", "mid-north", "Castilla y León, Burgos, Portugal Norte"),
    53000219534: ("Mid South", "mid-south", "Madrid periférico, Castilla-La Mancha, Valladolid"),
    53000219540: ("North", "north", "País Vasco, Cantabria, Asturias, Galicia Norte"),
    53000219519: ("Northwest", "northwest", "Asturias, Galicia Sur, Portugal"),
}

ROOT_REGION = ("Root", "root", "Sedes corporativas, delegaciones territoriales y SAT")

TENANT_INFO = {
    "name": "Edison Next Spain",
    "slug": "edison-next-spain",
    "description": "Propietario y gestor global de la infraestructura",
}

CUSTOM_FIELDS = [
    {
        "name": "alias",
        "label": "Alias de Sede",
        "type": "text",
        "object_types": ["dcim.site"],
        "description": "Nombre alternativo o comercial de la sede",
    },
    {
        "name": "alias_infra",
        "label": "Alias Infraestructura",
        "type": "text",
        "object_types": ["dcim.site"],
        "description": "Identificador técnico para sistemas de red y firewalls",
    },
]


def slugify(text: str) -> str:
    """Genera un slug kebab-case limpio compatible con NetBox."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def format_address(address_dict: Optional[Dict[str, Any]]) -> str:
    """Concatena los campos de dirección de Freshservice en una sola cadena."""
    if not address_dict:
        return ""
    parts = []
    for key in ["line1", "line2", "city", "state", "zipcode", "country"]:
        val = address_dict.get(key)
        if val and str(val).strip():
            parts.append(str(val).strip())
    return ", ".join(parts)


def format_comments(loc: Dict[str, Any]) -> str:
    """Genera bloque de comentarios con metadatos de contacto de Freshservice."""
    lines = [f"Freshservice Location ID: {loc.get('id')}"]
    contact = loc.get("contact_name")
    if contact:
        lines.append(f"Contacto: {contact}")
    email = loc.get("email")
    if email:
        lines.append(f"Email: {email}")
    phone = loc.get("phone")
    if phone:
        lines.append(f"Teléfono: {phone}")
    return "\n".join(lines)


def parse_locations_file(filepath: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parsea el archivo fresh-locations.json y retorna (tenant, regions, sites).
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_locations = data.get("locations", [])
    valid_locations = [l for l in raw_locations if l["id"] not in EXCLUDED_LOCATION_IDS]

    # Mapeo de agencias a regiones
    regions = []
    for name, slug, desc in AGENCY_REGION_MAPPING.values():
        regions.append({"name": name, "slug": slug, "description": desc})
    regions.append({"name": ROOT_REGION[0], "slug": ROOT_REGION[1], "description": ROOT_REGION[2]})

    # Agencias conocidas
    agency_ids = set(AGENCY_REGION_MAPPING.keys())

    sites = []
    slug_counts: Dict[str, int] = {}

    for loc in valid_locations:
        loc_id = loc["id"]
        # Las agencias principales no son sites físicos, son regiones
        if loc_id in agency_ids:
            continue

        parent_id = loc.get("parent_location_id")
        if parent_id in AGENCY_REGION_MAPPING:
            region_name, region_slug, _ = AGENCY_REGION_MAPPING[parent_id]
        else:
            region_name, region_slug, _ = ROOT_REGION

        name = loc["name"].strip()
        base_slug = slugify(name)
        
        # Manejo de slugs duplicados si existieran
        if base_slug in slug_counts:
            slug_counts[base_slug] += 1
            site_slug = f"{base_slug}-{slug_counts[base_slug]}"
        else:
            slug_counts[base_slug] = 1
            site_slug = base_slug

        site_payload = {
            "name": name,
            "slug": site_slug,
            "status": "active",
            "region_slug": region_slug,
            "region_name": region_name,
            "tenant_slug": TENANT_INFO["slug"],
            "physical_address": format_address(loc.get("address")),
            "comments": format_comments(loc),
            "custom_fields": {
                "alias": "",
                "alias_infra": "",
            },
            "freshservice_id": loc_id,
        }
        sites.append(site_payload)

    return TENANT_INFO, regions, sites
