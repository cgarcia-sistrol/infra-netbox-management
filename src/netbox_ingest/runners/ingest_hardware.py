#!/usr/bin/env python3
"""Script de ingesta para Fase 1: Catálogo de Hardware (Manufacturers, Roles, Platforms, Device Types)."""

import argparse
import os
import sys
from typing import Any, Dict, Optional

from netbox_ingest.client import NetBoxClient
from netbox_ingest.hardware_parser import (
    validate_hardware_catalog,
    get_catalog_summary,
)


def run_dry_run():
    """Muestra el resumen tabulado del catálogo de hardware a provisionar."""
    mfgs, roles, platforms, device_types = validate_hardware_catalog()
    summary = get_catalog_summary()

    print("=" * 80)
    print("RESUMEN DE CATÁLOGO DE HARDWARE - FASE 1 (DRY-RUN)")
    print("=" * 80)

    print(f"\n1. FABRICANTES ({summary['manufacturers_count']}):")
    for m in mfgs:
        print(f"   - {m['name']:<15} (slug: {m['slug']:<15}) -> {m['description']}")

    print(f"\n2. ROLES DE DISPOSITIVOS ({summary['roles_count']}):")
    for r in roles:
        print(f"   - {r['name']:<25} (slug: {r['slug']:<18}, color: #{r['color']}) -> {r['description']}")

    print(f"\n3. PLATAFORMAS ({summary['platforms_count']}):")
    for p in platforms:
        print(f"   - {p['name']:<18} (slug: {p['slug']:<15}, mfg: {p['manufacturer_slug']:<12}) -> {p['description']}")

    print(f"\n4. MODELOS DE HARDWARE / DEVICE TYPES ({summary['device_types_count']}):")
    print(f"{'Fabricante':<12} | {'Modelo':<28} | {'Slug':<28} | {'U':<4} | {'Ifaces':<6} | {'Cons':<4} | {'Pwr':<4}")
    print("-" * 96)
    for dt in device_types:
        if_count = len(dt.get("interfaces", []))
        con_count = len(dt.get("console_ports", []))
        pwr_count = len(dt.get("power_ports", []))
        print(
            f"{dt['manufacturer_slug']:<12} | "
            f"{dt['model']:<28} | "
            f"{dt['slug']:<28} | "
            f"{str(dt['u_height']):<4} | "
            f"{if_count:<6} | "
            f"{con_count:<4} | "
            f"{pwr_count:<4}"
        )

    print("\n" + "=" * 80)
    print("TOTALES A PROVISIONAR:")
    print(f" - Fabricantes: {summary['manufacturers_count']}")
    print(f" - Roles: {summary['roles_count']}")
    print(f" - Plataformas: {summary['platforms_count']}")
    print(f" - Tipos de Dispositivo: {summary['device_types_count']}")
    print(f" - Plantillas de Interfaces: {summary['total_interfaces']}")
    print(f" - Plantillas de Puertos Consola: {summary['total_console_ports']}")
    print(f" - Plantillas de Puertos Alimentación: {summary['total_power_ports']}")
    print("=" * 80)


def run_ingest(client: NetBoxClient):
    """Ejecuta la ingesta real e idempotente del catálogo de hardware en NetBox."""
    mfgs, roles, platforms, device_types = validate_hardware_catalog()

    print("[1/5] Conciliando Fabricantes (Manufacturers)...")
    mfg_map: Dict[str, int] = {}
    existing_mfgs = client.get_all("dcim/manufacturers")
    existing_mfg_by_slug = {m["slug"]: m for m in existing_mfgs}

    for m in mfgs:
        slug = m["slug"]
        if slug in existing_mfg_by_slug:
            mfg_id = existing_mfg_by_slug[slug]["id"]
            print(f"  [EXISTS] Fabricante: {m['name']} (ID: {mfg_id})")
        else:
            payload = {"name": m["name"], "slug": slug, "description": m["description"]}
            created = client.post("dcim/manufacturers", payload)
            mfg_id = created["id"]
            print(f"  [CREATED] Fabricante: {m['name']} (ID: {mfg_id})")
        mfg_map[slug] = mfg_id

    print("\n[2/5] Conciliando Roles de Dispositivo (Device Roles)...")
    role_map: Dict[str, int] = {}
    existing_roles = client.get_all("dcim/device-roles")
    existing_role_by_slug = {r["slug"]: r for r in existing_roles}

    for r in roles:
        slug = r["slug"]
        if slug in existing_role_by_slug:
            role_id = existing_role_by_slug[slug]["id"]
            print(f"  [EXISTS] Rol: {r['name']} (ID: {role_id})")
        else:
            payload = {
                "name": r["name"],
                "slug": slug,
                "color": r["color"],
                "description": r["description"],
                "vm_role": r.get("vm_role", False),
            }
            created = client.post("dcim/device-roles", payload)
            role_id = created["id"]
            print(f"  [CREATED] Rol: {r['name']} (ID: {role_id})")
        role_map[slug] = role_id

    print("\n[3/5] Conciliando Plataformas (Platforms)...")
    platform_map: Dict[str, int] = {}
    existing_platforms = client.get_all("dcim/platforms")
    existing_plat_by_slug = {p["slug"]: p for p in existing_platforms}

    for p in platforms:
        slug = p["slug"]
        mfg_id = mfg_map[p["manufacturer_slug"]]
        if slug in existing_plat_by_slug:
            plat_id = existing_plat_by_slug[slug]["id"]
            print(f"  [EXISTS] Plataforma: {p['name']} (ID: {plat_id})")
        else:
            payload = {
                "name": p["name"],
                "slug": slug,
                "manufacturer": mfg_id,
                "description": p["description"],
            }
            created = client.post("dcim/platforms", payload)
            plat_id = created["id"]
            print(f"  [CREATED] Plataforma: {p['name']} (ID: {plat_id})")
        platform_map[slug] = plat_id

    print("\n[4/5] Conciliando Modelos de Dispositivos (Device Types)...")
    existing_dts = client.get_all("dcim/device-types")
    existing_dt_by_slug = {dt["slug"]: dt for dt in existing_dts}

    dt_map: Dict[str, int] = {}
    for dt in device_types:
        slug = dt["slug"]
        mfg_id = mfg_map[dt["manufacturer_slug"]]
        plat_id = platform_map.get(dt.get("platform_slug")) if dt.get("platform_slug") else None

        if slug in existing_dt_by_slug:
            dt_id = existing_dt_by_slug[slug]["id"]
            print(f"  [EXISTS] Device Type: {dt['model']} (ID: {dt_id})")
        else:
            payload: Dict[str, Any] = {
                "manufacturer": mfg_id,
                "model": dt["model"],
                "slug": slug,
                "part_number": dt.get("part_number", ""),
                "u_height": dt.get("u_height", 0.0),
                "is_full_depth": dt.get("is_full_depth", False),
            }
            if plat_id:
                payload["default_platform"] = plat_id

            created = client.post("dcim/device-types", payload)
            dt_id = created["id"]
            print(f"  [CREATED] Device Type: {dt['model']} (ID: {dt_id})")

        dt_map[slug] = dt_id

    print("\n[5/5] Conciliando Plantillas de Componentes (Interfaces, Consola, Power)...")
    for dt in device_types:
        dt_id = dt_map[dt["slug"]]
        model_name = dt["model"]

        # Interfaces
        existing_ifaces = client.get_all("dcim/interface-templates", params={"device_type_id": dt_id})
        existing_iface_names = {i["name"] for i in existing_ifaces}
        for iface in dt.get("interfaces", []):
            if iface["name"] not in existing_iface_names:
                payload = {
                    "device_type": dt_id,
                    "name": iface["name"],
                    "type": iface["type"],
                    "mgmt_only": iface.get("mgmt_only", False),
                }
                client.post("dcim/interface-templates", payload)
                print(f"    + [IFACE] {model_name} -> {iface['name']} ({iface['type']})")

        # Console Ports
        existing_consoles = client.get_all("dcim/console-port-templates", params={"device_type_id": dt_id})
        existing_console_names = {c["name"] for c in existing_consoles}
        for cp in dt.get("console_ports", []):
            if cp["name"] not in existing_console_names:
                payload = {
                    "device_type": dt_id,
                    "name": cp["name"],
                    "type": cp["type"],
                }
                client.post("dcim/console-port-templates", payload)
                print(f"    + [CONSOLE] {model_name} -> {cp['name']} ({cp['type']})")

        # Power Ports
        existing_powers = client.get_all("dcim/power-port-templates", params={"device_type_id": dt_id})
        existing_power_names = {p["name"] for p in existing_powers}
        for pp in dt.get("power_ports", []):
            if pp["name"] not in existing_power_names:
                payload = {
                    "device_type": dt_id,
                    "name": pp["name"],
                    "type": pp["type"],
                }
                client.post("dcim/power-port-templates", payload)
                print(f"    + [POWER] {model_name} -> {pp['name']} ({pp['type']})")

    print("\n" + "=" * 80)
    print("[OK] Ingesta de Fase 1 completada con éxito.")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Ingesta de Fase 1: Catálogo de Hardware en NetBox")
    parser.add_argument("--dry-run", action="store_true", help="Ejecuta simulación y muestra resumen")
    parser.add_argument("--execute", action="store_true", help="Ejecuta la ingesta real contra NetBox")

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.print_help()
        sys.exit(1)

    if args.dry_run:
        run_dry_run()
    elif args.execute:
        client = NetBoxClient()
        run_ingest(client)


if __name__ == "__main__":
    main()
