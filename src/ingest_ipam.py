#!/usr/bin/env python3
"""Script principal para la ingesta de Redes y Jerarquía IPAM en NetBox (Fase 2)."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from netbox_ingest.client import NetBoxClient
from netbox_ingest.ipam_definitions import (
    IPAM_ROLES,
    VRFS,
    STANDARD_VLANS,
    HUB_SITES,
    SPOKE_SITES,
    GLOBAL_CONTAINER_PREFIXES,
    CLOUD_PREFIXES,
    INFRA_TRANSIT_PREFIXES,
    HUB_SPECIFIC_PREFIXES,
)


def generate_spoke_prefixes_and_vlans(
    spoke: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Genera el contenedor /16, el VLAN group, las 8 VLANs y sus 8 subredes /24 para una sede."""
    site_slug = spoke["site_slug"]
    site_name = spoke["site_name"]
    octet = spoke["second_octet"]

    # 1. VLAN Group
    vlan_group = {
        "name": f"VLAN-GROUP-{site_slug.upper()}",
        "slug": f"vlan-group-{site_slug}",
        "site_slug": site_slug,
        "site_name": site_name,
        "description": f"Dominio L2 local para {site_name} (Bloque 10.{octet}.0.0/16)",
    }

    # 2. VLANs y Subredes
    vlans: List[Dict[str, Any]] = []
    subnets: List[Dict[str, Any]] = []

    # Bloque contenedor de la sede
    site_container = {
        "prefix": f"10.{octet}.0.0/16",
        "status": "container",
        "role_slug": "supernet-container",
        "site_slug": site_slug,
        "description": f"Contenedor Sede: {site_name} (Bloque /16)",
    }

    for vlan_def in STANDARD_VLANS:
        vid = vlan_def["vid"]
        third = vlan_def["third_octet"]
        vlan_name = vlan_def["name"]
        role_slug = vlan_def["role_slug"]
        desc = vlan_def["description"]

        vlan_item = {
            "vid": vid,
            "name": f"{vlan_name}_{site_slug.upper()}",
            "slug": f"{vlan_def['role_slug']}-{site_slug}",
            "role_slug": role_slug,
            "site_slug": site_slug,
            "description": f"{desc} - {site_name}",
        }
        vlans.append(vlan_item)

        subnet_item = {
            "prefix": f"10.{octet}.{third}.0/24",
            "status": "active",
            "role_slug": role_slug,
            "site_slug": site_slug,
            "vlan_vid": vid,
            "vlan_name": vlan_item["name"],
            "description": f"{desc} [{site_name}]",
        }
        subnets.append(subnet_item)

    return site_container, vlans, subnets


def build_ipam_catalog() -> Dict[str, Any]:
    """Compila la totalidad de objetos IPAM a provisionar en NetBox."""
    all_vlan_groups: List[Dict[str, Any]] = []
    all_vlans: List[Dict[str, Any]] = []
    all_prefixes: List[Dict[str, Any]] = []

    # 1. Prefijos Globales
    all_prefixes.extend(GLOBAL_CONTAINER_PREFIXES)

    # 2. Prefijos Cloud
    all_prefixes.extend(CLOUD_PREFIXES)

    # 3. Hubs (Datacenters)
    for hub in HUB_SITES:
        h_slug = hub["slug"]
        h_name = hub["name"]
        h_octet = hub["second_octet"]

        # Contenedor /16
        all_prefixes.append({
            "prefix": f"10.{h_octet}.0.0/16",
            "status": "container",
            "role_slug": "supernet-container",
            "site_slug": h_slug,
            "description": f"Contenedor Centro de Datos: {h_name} (Bloque /16)",
        })

        # VLAN Group para Hub
        h_vg = {
            "name": f"VLAN-GROUP-{h_slug.upper()}",
            "slug": f"vlan-group-{h_slug}",
            "site_slug": h_slug,
            "site_name": h_name,
            "description": f"Dominio L2 local para {h_name} (Bloque 10.{h_octet}.0.0/16)",
        }
        all_vlan_groups.append(h_vg)

        # VLANs estándar en Hub
        for vlan_def in STANDARD_VLANS:
            all_vlans.append({
                "vid": vlan_def["vid"],
                "name": f"{vlan_def['name']}_{h_slug.upper()}",
                "slug": f"{vlan_def['role_slug']}-{h_slug}",
                "role_slug": vlan_def["role_slug"],
                "site_slug": h_slug,
                "description": f"{vlan_def['description']} - {h_name}",
            })

    # Subredes específicas de Hubs
    all_prefixes.extend(HUB_SPECIFIC_PREFIXES)

    # 4. Spokes
    for spoke in SPOKE_SITES:
        site_container, vlans, subnets = generate_spoke_prefixes_and_vlans(spoke)
        all_prefixes.append(site_container)
        all_vlan_groups.append({
            "name": f"VLAN-GROUP-{spoke['site_slug'].upper()}",
            "slug": f"vlan-group-{spoke['site_slug']}",
            "site_slug": spoke["site_slug"],
            "site_name": spoke["site_name"],
            "description": f"Dominio L2 local para {spoke['site_name']} (Bloque 10.{spoke['second_octet']}.0.0/16)",
        })
        all_vlans.extend(vlans)
        all_prefixes.extend(subnets)

    # 5. Overlays, BGP APIPA y VPN Pools
    all_prefixes.extend(INFRA_TRANSIT_PREFIXES)

    return {
        "roles": IPAM_ROLES,
        "vrfs": VRFS,
        "hub_sites": HUB_SITES,
        "vlan_groups": all_vlan_groups,
        "vlans": all_vlans,
        "prefixes": all_prefixes,
    }


def run_dry_run(export_path: Optional[str] = None) -> Dict[str, Any]:
    """Ejecuta simulación dry-run y presenta resumen tabulado de objetos IPAM."""
    catalog = build_ipam_catalog()

    print("=" * 90)
    print("RESUMEN DE PROVISIÓN IPAM Y REDES - FASE 2 (DRY-RUN)")
    print("=" * 90)

    print(f"\n1. ROLES IPAM ({len(catalog['roles'])}):")
    for r in catalog["roles"]:
        print(f"   - {r['name']:<28} (slug: {r['slug']:<24}, color: #{r['color']}) -> {r['description']}")

    print(f"\n2. VRFS ({len(catalog['vrfs'])}):")
    for v in catalog["vrfs"]:
        print(f"   - {v['name']:<20} (RD: {v['rd']:<12}) -> {v['description']}")

    print(f"\n3. CENTROS DE DATOS / HUBS ({len(catalog['hub_sites'])}):")
    for h in catalog["hub_sites"]:
        print(f"   - {h['name']:<20} (slug: {h['slug']:<15}, 2º octeto: 10.{h['second_octet']}.0.0/16)")

    print(f"\n4. GRUPOS DE VLAN (VLAN GROUPS) ({len(catalog['vlan_groups'])}):")
    print(f"   - Total grupos por Site creados: {len(catalog['vlan_groups'])}")
    for vg in catalog["vlan_groups"][:5]:
        print(f"     * {vg['name']:<35} -> Sede: {vg['site_slug']}")
    print("     * ...")

    print(f"\n5. VLANS ESTÁNDAR ({len(catalog['vlans'])}):")
    print(f"   - 8 VLANs estándar (VIDs 10, 20, 30, 40, 50, 60, 80, 90) por cada una de las {len(catalog['vlan_groups'])} sedes/hubs.")

    print(f"\n6. PREFIJOS Y JERARQUÍA IPAM ({len(catalog['prefixes'])}):")
    print(f"{'Prefijo CIDR':<24} | {'Estado':<10} | {'Rol':<22} | {'Sede / Destino':<25}")
    print("-" * 90)
    for p in catalog["prefixes"][:25]:
        site_info = p.get("site_slug") or p.get("vrf_name") or "Global"
        print(f"{p['prefix']:<24} | {p['status']:<10} | {p['role_slug']:<22} | {site_info:<25}")
    print(f"... y {len(catalog['prefixes']) - 25} prefijos adicionales.")

    print("\n" + "=" * 90)
    print("TOTALES DE OBJETOS A PROVISIONAR:")
    print(f" - Roles IPAM: {len(catalog['roles'])}")
    print(f" - VRFs: {len(catalog['vrfs'])}")
    print(f" - VLAN Groups (por Sede): {len(catalog['vlan_groups'])}")
    print(f" - VLANs individuales: {len(catalog['vlans'])}")
    print(f" - Prefijos CIDR: {len(catalog['prefixes'])}")
    print("=" * 90)

    if export_path:
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Catálogo IPAM exportado exitosamente a: {export_path}")

    return catalog


def run_ingest(client: NetBoxClient, export_path: Optional[str] = None):
    """Ejecuta el aprovisionamiento real e idempotente de la Fase 2 en NetBox."""
    catalog = build_ipam_catalog()
    print("Iniciando aprovisionamiento de Fase 2 (Redes e IPAM) en NetBox...")

    # 1. Asegurar Sedes Hubs (Madrid CPD y JESP)
    print("\n--- 1. Verificando / Creando Sedes de Centros de Datos (Hubs) ---")
    site_id_map: Dict[str, int] = {}
    for hub in catalog["hub_sites"]:
        try:
            existing = client.get("dcim/sites", params={"slug": hub["slug"]})
            if existing.get("count", 0) > 0:
                site_id = existing["results"][0]["id"]
                site_id_map[hub["slug"]] = site_id
                print(f"   [EXISTE] Site '{hub['name']}' (ID: {site_id})")
            else:
                site_payload = {
                    "name": hub["name"],
                    "slug": hub["slug"],
                    "status": "active",
                    "description": hub["description"],
                }
                res = client.post("dcim/sites", site_payload)
                site_id = res["id"]
                site_id_map[hub["slug"]] = site_id
                print(f"   [CREADO] Site '{hub['name']}' (ID: {site_id})")
        except Exception as e:
            print(f"   [ERROR] Site '{hub['name']}': {e}")

    # Cargar el resto de Sites existentes en NetBox
    try:
        all_sites = client.get_all("dcim/sites")
        for s in all_sites:
            site_id_map[s["slug"]] = s["id"]
    except Exception as e:
        print(f"   [AVISO] No se pudo precargar mapa de sitios: {e}")

    # 2. Roles IPAM
    print("\n--- 2. Verificando / Creando Roles IPAM ---")
    role_id_map: Dict[str, int] = {}
    for r in catalog["roles"]:
        try:
            existing = client.get("ipam/roles", params={"slug": r["slug"]})
            if existing.get("count", 0) > 0:
                role_id = existing["results"][0]["id"]
                role_id_map[r["slug"]] = role_id
                print(f"   [EXISTE] Role IPAM '{r['name']}' (ID: {role_id})")
            else:
                payload = {
                    "name": r["name"],
                    "slug": r["slug"],
                    "color": r.get("color", "9e9e9e"),
                    "description": r.get("description", ""),
                }
                res = client.post("ipam/roles", payload)
                role_id = res["id"]
                role_id_map[r["slug"]] = role_id
                print(f"   [CREADO] Role IPAM '{r['name']}' (ID: {role_id})")
        except Exception as e:
            print(f"   [ERROR] Role IPAM '{r['name']}': {e}")

    # 3. VRFs
    print("\n--- 3. Verificando / Creando VRFs ---")
    vrf_id_map: Dict[str, int] = {}
    for v in catalog["vrfs"]:
        try:
            existing = client.get("ipam/vrfs", params={"name": v["name"]})
            if existing.get("count", 0) > 0:
                vrf_id = existing["results"][0]["id"]
                vrf_id_map[v["name"]] = vrf_id
                print(f"   [EXISTE] VRF '{v['name']}' (ID: {vrf_id})")
            else:
                payload = {
                    "name": v["name"],
                    "rd": v.get("rd"),
                    "description": v.get("description", ""),
                }
                res = client.post("ipam/vrfs", payload)
                vrf_id = res["id"]
                vrf_id_map[v["name"]] = vrf_id
                print(f"   [CREADO] VRF '{v['name']}' (ID: {vrf_id})")
        except Exception as e:
            print(f"   [ERROR] VRF '{v['name']}': {e}")

    # 4. VLAN Groups (por Sede)
    print("\n--- 4. Verificando / Creando VLAN Groups por Sede ---")
    vlan_group_id_map: Dict[str, int] = {}
    for vg in catalog["vlan_groups"]:
        site_slug = vg.get("site_slug")
        site_id = site_id_map.get(site_slug)
        try:
            existing = client.get("ipam/vlan-groups", params={"slug": vg["slug"]})
            if existing.get("count", 0) > 0:
                vg_id = existing["results"][0]["id"]
                vlan_group_id_map[vg["slug"]] = vg_id
                print(f"   [EXISTE] VLAN Group '{vg['name']}' (ID: {vg_id})")
            else:
                payload = {
                    "name": vg["name"],
                    "slug": vg["slug"],
                    "description": vg.get("description", ""),
                }
                if site_id:
                    payload["scope_type"] = "dcim.site"
                    payload["scope_id"] = site_id

                res = client.post("ipam/vlan-groups", payload)
                vg_id = res["id"]
                vlan_group_id_map[vg["slug"]] = vg_id
                print(f"   [CREADO] VLAN Group '{vg['name']}' (ID: {vg_id})")
        except Exception as e:
            print(f"   [ERROR] VLAN Group '{vg['name']}': {e}")

    # 5. VLANs
    print("\n--- 5. Verificando / Creando VLANs Estándar ---")
    vlan_key_map: Dict[Tuple[str, int], int] = {}
    for vlan in catalog["vlans"]:
        site_slug = vlan.get("site_slug", "")
        site_id = site_id_map.get(site_slug)
        vg_slug = f"vlan-group-{site_slug}"
        vg_id = vlan_group_id_map.get(vg_slug)
        role_id = role_id_map.get(vlan.get("role_slug", ""))
        vid = vlan["vid"]

        query_params = {"vid": vid}
        if vg_id:
            query_params["group_id"] = vg_id
        elif site_id:
            query_params["site_id"] = site_id

        try:
            existing = client.get("ipam/vlans", params=query_params)
            if existing.get("count", 0) > 0:
                vlan_id = existing["results"][0]["id"]
                vlan_key_map[(site_slug, vid)] = vlan_id
                print(f"   [EXISTE] VLAN {vid} ({vlan['name']}) [ID: {vlan_id}]")
            else:
                payload = {
                    "vid": vid,
                    "name": vlan["name"],
                    "status": "active",
                    "description": vlan.get("description", ""),
                }
                if site_id:
                    payload["site"] = site_id
                if vg_id:
                    payload["group"] = vg_id
                if role_id:
                    payload["role"] = role_id

                res = client.post("ipam/vlans", payload)
                vlan_id = res["id"]
                vlan_key_map[(site_slug, vid)] = vlan_id
                print(f"   [CREADO] VLAN {vid} ({vlan['name']}) [ID: {vlan_id}]")
        except Exception as e:
            print(f"   [ERROR] VLAN {vid} ({vlan['name']}): {e}")

    # 6. Prefijos
    print("\n--- 6. Verificando / Creando Prefijos IPAM ---")
    for pref in catalog["prefixes"]:
        cidr = pref["prefix"]
        site_slug = pref.get("site_slug", "")
        site_id = site_id_map.get(site_slug) if site_slug else None
        role_id = role_id_map.get(pref.get("role_slug", ""))
        vrf_id = vrf_id_map.get(pref.get("vrf_name", ""))
        vlan_vid = pref.get("vlan_vid")
        vlan_id = vlan_key_map.get((site_slug, vlan_vid)) if (site_slug and vlan_vid) else None

        query_params = {"prefix": cidr}
        if vrf_id:
            query_params["vrf_id"] = vrf_id

        try:
            existing = client.get("ipam/prefixes", params=query_params)
            if existing.get("count", 0) > 0:
                p_id = existing["results"][0]["id"]
                print(f"   [EXISTE] Prefix {cidr:<18} (ID: {p_id}) [{pref.get('role_slug', 'N/A')}]")
            else:
                payload = {
                    "prefix": cidr,
                    "status": pref.get("status", "active"),
                    "description": pref.get("description", ""),
                }
                if site_id:
                    payload["site"] = site_id
                if role_id:
                    payload["role"] = role_id
                if vrf_id:
                    payload["vrf"] = vrf_id
                if vlan_id:
                    payload["vlan"] = vlan_id

                res = client.post("ipam/prefixes", payload)
                p_id = res["id"]
                print(f"   [CREADO] Prefix {cidr:<18} (ID: {p_id}) [{pref.get('role_slug', 'N/A')}]")
        except Exception as e:
            print(f"   [ERROR] Prefix {cidr}: {e}")

    print("\n" + "=" * 90)
    print("[FINALIZADO] Provisión de Fase 2 completada con éxito.")
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Ingesta de Redes e IPAM en NetBox (Fase 2)")
    parser.add_argument("--dry-run", action="store_true", help="Simulación de ingesta sin aplicar cambios")
    parser.add_argument("--export-json", type=str, default=None, help="Ruta para exportar el catálogo IPAM compilado en JSON")
    parser.add_argument("--url", type=str, default=os.getenv("NETBOX_URL", "https://netbox.infra.edison.es"), help="URL base de NetBox")
    parser.add_argument("--token", type=str, default=os.getenv("NETBOX_TOKEN", ""), help="Token de autenticación API NetBox")

    args = parser.parse_args()

    if args.dry_run:
        run_dry_run(export_path=args.export_json)
    else:
        if not args.token:
            print("[ERROR] Se requiere el token de NetBox (--token o NETBOX_TOKEN en entorno) para ejecutar la ingesta.", file=sys.stderr)
            sys.exit(1)
        client = NetBoxClient(base_url=args.url, token=args.token)
        run_ingest(client=client, export_path=args.export_json)


if __name__ == "__main__":
    main()
