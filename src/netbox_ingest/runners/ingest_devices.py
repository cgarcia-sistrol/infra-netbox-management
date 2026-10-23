#!/usr/bin/env python3
"""Script de ingesta para Fase 4: Despliegue de Equipamiento Físico y DCIM en NetBox.

Crea de forma idempotente:
- 33 Firewalls FortiGate vinculados a sus sedes
- 39 FortiSwitches vinculados a sus sedes y ubicaciones (P2/C2 en JESP, Oficinas/Talleres en IVECO, etc.)
- 1 Servidor Físico HPE DL360 Gen11 en Madrid CPD (Rack F2R4)
- Guarda registro de conciliación en inputs/hardware_ingest_summary.json
"""

import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional

from netbox_ingest.client import NetBoxClient

# Mapeo unívoco de nombres de Firewalls a Sites en NetBox
FGT_SITE_MAPPING = {
    "FGT100-JES": "Oficina Madrid - Esplandiú",
    "FortiGate-100F": "Madrid CPD",
    "FGT60F-ADH": "Delegación Alcalá De Henares",
    "FGT60F-ARC-AVI": "ArcelorMittal Avilés",
    "FGT60F-ARC-GIJ": "ArcelorMittal Veriña",
    "FGT60F-COR-ARR": "COREN ROLLS",
    "FGT60F-COR-SCI": "COREN CAT",
    "FGT60F-DAMM": "DAMM",
    "FGT60F-EAMSA": "EAMSA",
    "FGT60F-EPZ": "EL POZO",
    "FGT60F-FOM": "Fompedraza",
    "FGT60F-FONZ": "Guijuelo Fonz",
    "FGT60F-GIJ-OFI": "Oficina Gijón",
    "FGT60F-IBZ": "Delegación Ibiza",
    "FGT60F-ILAS": "ILAS Reny Picot",
    "FGT60F-INLEIT": "INLEIT",
    "FGT60F-LCA": "Leche Celta Ávila",
    "FGT60F-LCM": "Leche Celta Meruelo",
    "FGT60F-LCP": "Leche Celta Pontedeume",
    "FGT60F-MDR": "Delegación Molins De Rei",
    "FGT60F-MILAGROS": "Guijuelo Milagros",
    "FGT60F-MONZON": "Guijuelo Monzón",
    "FGT60F-PBF": "PackBenefit",
    "FGT60F-PDM": "Delegación Palma De Mallorca",
    "FGT60F-SANMILLAN": "Guijuelo San Millan",
    "FGT60F-SBL": "Delegación Sant Boi De Llobregat",
    "FGT60F-SCV": "Delegación Sant Cugat Del Vallès",
    "FGT60F-SEV": "Delegación Sevilla",
    "FGT60F-TEST-JESP": "TEST-JESP",
    "FGT60F-ZNF": "Delegación Barcelona - Zona Franca",
    "FGT60F-IVECO-MAD": "IVECO Madrid",
    "FGT60F-IVECO-VALL": "IVECO Valladolid",
    "FGT60F-ALM": "Delegación Almería",
}

MANAGED_FILES = [
    ("inputs/managed_devices_FW-HUB-GF_2026-10-14-200015.csv", "FW-HUB-GF"),
    ("inputs/managed_devices_FW-SPOKE-STD-DEPLOY_2026-10-14-195934.csv", "FW-SPOKE-STD-DEPLOY"),
    ("inputs/managed_devices_FW-SPOKE_2026-10-14-200622.csv", "FW-SPOKE"),
    ("inputs/managed_devices_FW-LEGACY_2026-10-14-200637.csv", "FW-LEGACY"),
]


def load_products_catalog() -> Dict[str, Dict[str, str]]:
    """Carga el catálogo de productos oficiales (fuente de verdad de S/N)."""
    products = {}
    path = "inputs/fortinet-products_14_10_2026.csv"
    if os.path.exists(path):
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            for r in reader:
                sn = r["Serial Number"].strip()
                products[sn] = r
    return products


def parse_managed_csvs() -> List[Dict[str, Any]]:
    """Extrae la estructura de Firewalls y sus switches asociados."""
    all_fgts = []

    for path, adom in MANAGED_FILES:
        if not os.path.exists(path):
            continue
        with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.reader(f)
            _ = next(reader, None)
            current_fgt = None
            for row in reader:
                if not row or not any(row):
                    continue
                raw_name = row[0]
                name = raw_name.strip()
                is_switch = raw_name.startswith("        ") or "SW-" in name or name.startswith("S2") or name.startswith("S1")
                if raw_name.strip() == "FSW":
                    continue

                serial = row[8].strip() if len(row) > 8 else ""
                platform = row[5].strip() if len(row) > 5 else ""
                ip = row[4].strip() if len(row) > 4 else ""
                hostname = row[3].strip() if len(row) > 3 else ""
                desc = row[6].strip() if len(row) > 6 else ""

                if not is_switch and (name.startswith("FGT") or platform.startswith("FortiGate")):
                    current_fgt = {
                        "adom": adom,
                        "type": "firewall",
                        "name": name,
                        "hostname": hostname,
                        "serial": serial,
                        "platform": platform,
                        "ip": ip,
                        "desc": desc,
                        "switches": [],
                    }
                    all_fgts.append(current_fgt)
                elif is_switch and current_fgt is not None:
                    current_fgt["switches"].append({
                        "adom": adom,
                        "type": "switch",
                        "name": name,
                        "hostname": hostname,
                        "serial": serial,
                        "platform": platform,
                        "parent": current_fgt["name"],
                    })

    # Regla de depuración TEST-JESP: solo switch S248DNTF24000446
    for f in all_fgts:
        if f["name"] == "FGT60F-TEST-JESP":
            f["switches"] = [s for s in f["switches"] if s["serial"] == "S248DNTF24000446"]

    return all_fgts


def main():
    print("=" * 80)
    print("INICIANDO INGESTA DCIM / EQUIPAMIENTO FÍSICO (FASE 4)")
    print("=" * 80)

    client = NetBoxClient()
    products = load_products_catalog()
    fgts = parse_managed_csvs()

    # Cargar diccionarios de NetBox
    sites = {s["name"]: s for s in client.get_all("dcim/sites")}
    locs = client.get_all("dcim/locations")
    loc_by_site_name = {(l["site"]["id"], l["name"]): l for l in locs}
    device_types = {dt["model"]: dt for dt in client.get_all("dcim/device-types")}
    roles = {r["slug"]: r for r in client.get_all("dcim/device-roles")}
    platforms = {p["slug"]: p for p in client.get_all("dcim/platforms")}
    racks = {r["name"]: r for r in client.get_all("dcim/racks")}

    # Mapa de dispositivos existentes por nombre
    existing_devices = {d["name"]: d for d in client.get_all("dcim/devices")}

    results = {
        "created_devices": [],
        "updated_devices": [],
        "errors": [],
    }

    # 1. Ingestar Servidor EDISON-SERVER1 en Madrid CPD
    cpd_site = sites.get("Madrid CPD")
    cpd_loc = loc_by_site_name.get((cpd_site["id"], "InterXion-MAD2.321")) if cpd_site else None
    rack_f2r4 = racks.get("F2R4")
    dl360_dt = device_types.get("HPE ProLiant DL360 Gen11")
    mgmt_role = roles.get("management")

    server_name = "EDISON-SERVER1"
    server_serial = "CZJD0V03B4"
    if server_name in existing_devices:
        print(f"[EXISTS] Servidor: {server_name}")
    else:
        try:
            payload = {
                "name": server_name,
                "device_type": dl360_dt["id"],
                "role": mgmt_role["id"],
                "site": cpd_site["id"],
                "location": cpd_loc["id"] if cpd_loc else None,
                "rack": rack_f2r4["id"] if rack_f2r4 else None,
                "position": 1,
                "face": "front",
                "status": "active",
                "serial": server_serial,
                "description": "Servidor Sarenet InterXion-MAD2.321 Rack F2R4",
            }
            d_created = client.post("dcim/devices", payload)
            print(f"[CREATED] Servidor: {server_name} (ID: {d_created['id']})")
            results["created_devices"].append(server_name)
        except Exception as e:
            print(f"[ERROR] Servidor {server_name}: {e}")
            results["errors"].append({"device": server_name, "error": str(e)})

    # 2. Ingestar Firewalls y Switches
    fw_role = roles.get("firewall")
    sw_role = roles.get("switch")
    fortios_plat = platforms.get("fortios")
    fortiswitch_plat = platforms.get("fortiswitchos")

    for fgt in fgts:
        fgt_name = fgt["name"]
        site_name = FGT_SITE_MAPPING.get(fgt_name)
        if not site_name or site_name not in sites:
            print(f"[WARN] No se encontró Site para {fgt_name} (mapeado: {site_name})")
            results["errors"].append({"device": fgt_name, "error": f"Site no encontrado: {site_name}"})
            continue

        site_obj = sites[site_name]
        site_id = site_obj["id"]

        # Determinar modelo y S/N oficial
        fgt_serial = fgt["serial"]
        fgt_model = fgt["platform"]
        if fgt_serial in products:
            prod_info = products[fgt_serial]
            fgt_model = prod_info.get("Product Model", fgt_model)

        dt_obj = device_types.get(fgt_model)
        if not dt_obj:
            print(f"[ERROR] Device Type no encontrado: {fgt_model} para {fgt_name}")
            results["errors"].append({"device": fgt_name, "error": f"DeviceType no encontrado: {fgt_model}"})
            continue

        # Determinar Location y Rack
        fgt_loc_id = None
        fgt_rack_id = None
        fgt_position = None

        if fgt_name == "FortiGate-100F" and site_name == "Madrid CPD":
            fgt_loc = loc_by_site_name.get((site_id, "InterXion-MAD2.321"))
            fgt_loc_id = fgt_loc["id"] if fgt_loc else None
            fgt_rack_id = rack_f2r4["id"] if rack_f2r4 else None
            fgt_position = 2  # Asignado en 1U independiente en rack
        elif site_name == "Oficina Madrid - Esplandiú":
            p2_loc = loc_by_site_name.get((site_id, "P2"))
            fgt_loc_id = p2_loc["id"] if p2_loc else None
        elif site_name == "IVECO Madrid":
            ofi_loc = loc_by_site_name.get((site_id, "Oficinas"))
            fgt_loc_id = ofi_loc["id"] if ofi_loc else None
        elif site_name == "IVECO Valladolid":
            ofi_loc = loc_by_site_name.get((site_id, "Oficinas"))
            fgt_loc_id = ofi_loc["id"] if ofi_loc else None

        # Instanciar Firewall
        if fgt_name in existing_devices:
            print(f"[EXISTS] Firewall: {fgt_name}")
        else:
            try:
                payload = {
                    "name": fgt_name,
                    "device_type": dt_obj["id"],
                    "role": fw_role["id"],
                    "site": site_id,
                    "location": fgt_loc_id,
                    "rack": fgt_rack_id,
                    "position": fgt_position,
                    "face": "front" if fgt_rack_id else None,
                    "status": "active",
                    "serial": fgt_serial,
                    "platform": fortios_plat["id"] if fortios_plat else None,
                    "description": fgt.get("desc", ""),
                }
                d_created = client.post("dcim/devices", payload)
                print(f"[CREATED] Firewall: {fgt_name} en {site_name} (ID: {d_created['id']})")
                results["created_devices"].append(fgt_name)
            except Exception as e:
                print(f"[ERROR] Creando firewall {fgt_name}: {e}")
                results["errors"].append({"device": fgt_name, "error": str(e)})

        # 3. Instanciar Switches dependientes
        for sw in fgt["switches"]:
            sw_name = sw["name"]
            sw_serial = sw["serial"]
            sw_model = sw["platform"]

            if sw_serial in products:
                prod_info = products[sw_serial]
                sw_model = prod_info.get("Product Model", sw_model)

            sw_dt_obj = device_types.get(sw_model)
            if not sw_dt_obj:
                print(f"[ERROR] Device Type no encontrado: {sw_model} para switch {sw_name}")
                results["errors"].append({"device": sw_name, "error": f"DeviceType no encontrado: {sw_model}"})
                continue

            # Determinar Location del switch
            sw_loc_id = None
            if site_name == "Oficina Madrid - Esplandiú":
                if "05" in sw_name or sw_serial == "S248DNTF24000237":
                    c2_loc = loc_by_site_name.get((site_id, "C2"))
                    sw_loc_id = c2_loc["id"] if c2_loc else None
                else:
                    p2_loc = loc_by_site_name.get((site_id, "P2"))
                    sw_loc_id = p2_loc["id"] if p2_loc else None
            elif site_name == "IVECO Madrid":
                ofi_loc = loc_by_site_name.get((site_id, "Oficinas"))
                sw_loc_id = ofi_loc["id"] if ofi_loc else None
            elif site_name == "IVECO Valladolid":
                if "01" in sw_name or sw_serial == "S248EPTF23007194":
                    loc = loc_by_site_name.get((site_id, "Oficinas"))
                    sw_loc_id = loc["id"] if loc else None
                elif "02" in sw_name or sw_serial == "S224ENTF25000462":
                    loc = loc_by_site_name.get((site_id, "Taller Pintura"))
                    sw_loc_id = loc["id"] if loc else None
                elif "03" in sw_name or sw_serial == "S224EPTF23012092":
                    loc = loc_by_site_name.get((site_id, "Taller Chapa"))
                    sw_loc_id = loc["id"] if loc else None

            if sw_name in existing_devices:
                print(f"[EXISTS] Switch: {sw_name}")
            else:
                try:
                    payload = {
                        "name": sw_name,
                        "device_type": sw_dt_obj["id"],
                        "role": sw_role["id"],
                        "site": site_id,
                        "location": sw_loc_id,
                        "status": "active",
                        "serial": sw_serial,
                        "platform": fortiswitch_plat["id"] if fortiswitch_plat else None,
                        "description": f"Switch gestionado vía {fgt_name}",
                    }
                    sw_created = client.post("dcim/devices", payload)
                    print(f"[CREATED] Switch: {sw_name} ({sw_model}) en {site_name} (ID: {sw_created['id']})")
                    results["created_devices"].append(sw_name)
                except Exception as e:
                    print(f"[ERROR] Creando switch {sw_name}: {e}")
                    results["errors"].append({"device": sw_name, "error": str(e)})

    # Guardar resumen en inputs/hardware_ingest_summary.json
    summary_path = "inputs/hardware_ingest_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("RESUMEN DE INGESTA DCIM:")
    print(f" - Dispositivos Creados: {len(results['created_devices'])}")
    print(f" - Errores: {len(results['errors'])}")
    print(f" - Resumen guardado en: {summary_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
