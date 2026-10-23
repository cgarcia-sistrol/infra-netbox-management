#!/usr/bin/env python3
"""Script principal para la ingesta de la estructura organizativa en NetBox."""

import argparse
import json
import os
import sys

from netbox_ingest.parser import (
    parse_locations_file,
    CUSTOM_FIELDS,
)
from netbox_ingest.client import NetBoxClient
from typing import Optional


def run_dry_run(json_path: str, export_path: Optional[str] = None):
    """Ejecuta dry-run y muestra resumen tabulado de objetos a provisionar."""
    tenant, regions, sites = parse_locations_file(json_path)

    print("=" * 80)
    print("RESUMEN DE OBJETOS A PROVISIONAR EN NETBOX (DRY-RUN)")
    print("=" * 80)

    print(f"\n1. TENANT ({1}):")
    print(f"   - Nombre: {tenant['name']}")
    print(f"   - Slug: {tenant['slug']}")
    print(f"   - Descripción: {tenant['description']}")

    print(f"\n2. CUSTOM FIELDS EN dcim.site ({len(CUSTOM_FIELDS)}):")
    for cf in CUSTOM_FIELDS:
        print(f"   - {cf['name']} ({cf['type']}) -> {cf['label']} [{cf['description']}]")

    print(f"\n3. REGIONES ({len(regions)}):")
    for r in regions:
        region_sites = [s for s in sites if s["region_slug"] == r["slug"]]
        print(f"   - {r['name']:<18} (slug: {r['slug']:<15}) -> {len(region_sites):2d} sedes")

    print(f"\n4. SITES ({len(sites)}):")
    print(f"{'Nombre Sede':<35} | {'Región':<15} | {'Slug':<30}")
    print("-" * 85)
    for s in sites:
        print(f"{s['name']:<35} | {s['region_name']:<15} | {s['slug']:<30}")

    payload = {
        "tenant": tenant,
        "custom_fields": CUSTOM_FIELDS,
        "regions": regions,
        "sites": sites,
    }

    if export_path:
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Datos exportados a: {export_path}")

    return payload


def run_ingest(client: NetBoxClient, json_path: str):
    """Ejecuta la ingesta real contra la API de NetBox de forma idempotente."""
    tenant, regions, sites = parse_locations_file(json_path)

    print("Iniciando aprovisionamiento en NetBox...")

    # 1. Custom Fields
    print("\n--- 1. Verificando / Creando Custom Fields ---")
    for cf in CUSTOM_FIELDS:
        try:
            existing = client.get("extras/custom-fields", params={"name": cf["name"]})
            if existing.get("count", 0) > 0:
                print(f"   [EXISTE] Custom field '{cf['name']}'")
            else:
                client.post("extras/custom-fields", cf)
                print(f"   [CREADO] Custom field '{cf['name']}'")
        except Exception as e:
            print(f"   [ERROR] Custom field '{cf['name']}': {e}")

    # 2. Tenant
    print("\n--- 2. Verificando / Creando Tenant ---")
    tenant_id = None
    try:
        existing_tenants = client.get("tenancy/tenants", params={"slug": tenant["slug"]})
        if existing_tenants.get("count", 0) > 0:
            tenant_id = existing_tenants["results"][0]["id"]
            print(f"   [EXISTE] Tenant '{tenant['name']}' (ID: {tenant_id})")
        else:
            res = client.post("tenancy/tenants", tenant)
            tenant_id = res["id"]
            print(f"   [CREADO] Tenant '{tenant['name']}' (ID: {tenant_id})")
    except Exception as e:
        print(f"   [ERROR] Tenant '{tenant['name']}': {e}")

    # 3. Regiones
    print("\n--- 3. Verificando / Creando Regiones ---")
    region_id_map = {}
    for r in regions:
        try:
            existing = client.get("dcim/regions", params={"slug": r["slug"]})
            if existing.get("count", 0) > 0:
                rid = existing["results"][0]["id"]
                region_id_map[r["slug"]] = rid
                print(f"   [EXISTE] Región '{r['name']}' (ID: {rid})")
            else:
                res = client.post("dcim/regions", r)
                rid = res["id"]
                region_id_map[r["slug"]] = rid
                print(f"   [CREADO] Región '{r['name']}' (ID: {rid})")
        except Exception as e:
            print(f"   [ERROR] Región '{r['name']}': {e}")

    # 4. Sites
    print("\n--- 4. Verificando / Creando Sites ---")
    created_count = 0
    existing_count = 0
    error_count = 0

    for s in sites:
        site_payload = {
            "name": s["name"],
            "slug": s["slug"],
            "status": s["status"],
            "region": region_id_map.get(s["region_slug"]),
            "tenant": tenant_id,
            "physical_address": s["physical_address"],
            "comments": s["comments"],
            "custom_fields": s["custom_fields"],
        }
        try:
            existing = client.get("dcim/sites", params={"slug": s["slug"]})
            if existing.get("count", 0) > 0:
                existing_count += 1
                print(f"   [EXISTE] Site '{s['name']}'")
            else:
                client.post("dcim/sites", site_payload)
                created_count += 1
                print(f"   [CREADO] Site '{s['name']}' ({s['region_name']})")
        except Exception as e:
            error_count += 1
            print(f"   [ERROR] Site '{s['name']}': {e}")

    print(f"\nResumen de Sites: {created_count} creados, {existing_count} existentes, {error_count} errores.")


def main():
    parser = argparse.ArgumentParser(description="Ingesta de Organización Freshservice a NetBox")
    parser.add_argument("--input", default="inputs/fresh-locations.json", help="Ruta al archivo fresh-locations.json")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Ejecutar en modo dry-run")
    parser.add_argument("--export-json", default="inputs/netbox_payload_organization.json", help="Exportar payload JSON consolidado")
    parser.add_argument("--execute", action="store_true", help="Ejecutar mutaciones contra la API de NetBox")

    args = parser.parse_args()

    if args.execute:
        client = NetBoxClient()
        run_ingest(client, args.input)
    else:
        run_dry_run(args.input, args.export_json)


if __name__ == "__main__":
    main()
