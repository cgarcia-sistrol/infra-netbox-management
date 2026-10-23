#!/usr/bin/env python3
"""Script de ingesta idempotente para Wireless LANs (SSIDs) y asignación a APs en NetBox.

Crea y concilia:
- 3 Wireless LAN Groups: 'Corporativo', 'Invitados', 'OT & Servicios'.
- 8 Wireless LANs (SSIDs) con su tipo de autenticación y cifrado.
- Interfaz inalámbrica 'wlan0' en cada uno de los 56 APs con su estándar 802.11 y lista de wireless_lans.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

from netbox_ingest.client import NetBoxClient

# Grupos de Wireless LAN
WIRELESS_LAN_GROUPS: Dict[str, Dict[str, str]] = {
    "corporativo": {
        "name": "Corporativo",
        "slug": "corporativo",
        "description": "Redes WiFi corporativas de empleado",
    },
    "invitados": {
        "name": "Invitados",
        "slug": "invitados",
        "description": "Redes WiFi de invitados y visitas externas",
    },
    "ot-servicios": {
        "name": "OT & Servicios",
        "slug": "ot-servicios",
        "description": "Redes WiFi para CCTV, Impresoras, IoT y entornos industriales",
    },
}

# 8 SSIDs descubiertos en UniFi
WIRELESS_LANS: List[Dict[str, Any]] = [
    {
        "ssid": "EDISON_NEXT",
        "group_slug": "corporativo",
        "auth_type": "wpa-personal",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi Corporativa principal WPA2-Personal (VLAN 11 / Multisede)",
    },
    {
        "ssid": "INVITADOS_EDISON_NEXT",
        "group_slug": "invitados",
        "auth_type": "wpa-personal",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi de invitados y visitas aislada (VLAN 20 / Multisede)",
    },
    {
        "ssid": "EDISON_NEXT_",
        "group_slug": "corporativo",
        "auth_type": "wpa-enterprise",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi Corporativa 802.1X / RADIUS (VLAN 11 / Esplandiú)",
    },
    {
        "ssid": "EDISON_NEXT_WIOT",
        "group_slug": "ot-servicios",
        "auth_type": "wpa-personal",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi IoT / Industrial (IVECO Valladolid)",
    },
    {
        "ssid": "EDISON_NEXT_CCTV",
        "group_slug": "ot-servicios",
        "auth_type": "wpa-personal",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi para videovigilancia y cámaras CCTV (VLAN 40 / PackBenefit)",
    },
    {
        "ssid": "EDISON_NEXT_PRINT",
        "group_slug": "ot-servicios",
        "auth_type": "wpa-personal",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi para impresoras y multifuncionales (VLAN 30 / ILAS)",
    },
    {
        "ssid": "FENICE-VALLADOLID",
        "group_slug": "ot-servicios",
        "auth_type": "wpa-personal",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi OT planta IVECO Valladolid",
    },
    {
        "ssid": "FENICE-VALL-GUEST",
        "group_slug": "invitados",
        "auth_type": "wpa-personal",
        "auth_cipher": "aes",
        "status": "active",
        "description": "Red WiFi Invitados local IVECO Valladolid",
    },
]

# Mapeo de modelo UniFi a estándar IEEE 802.11
MODEL_TO_WIFI_TYPE: Dict[str, str] = {
    "U7PRO": "ieee802.11be",   # Wi-Fi 7
    "UKPW": "ieee802.11be",    # Wi-Fi 7 (U7-Outdoor)
    "UALR6v2": "ieee802.11ax", # Wi-Fi 6 (U6-LR)
    "U6M": "ieee802.11ax",     # Wi-Fi 6 (U6-Mesh)
    "UAP6MP": "ieee802.11ax",  # Wi-Fi 6 (U6-Pro)
    "U7PG2": "ieee802.11ac",   # Wi-Fi 5 (AP-AC-Pro)
    "U7LR": "ieee802.11ac",    # Wi-Fi 5 (AP-AC-LR)
}


def get_wifi_interface_type(model_code: str) -> str:
    """Devuelve el tipo de interfaz inalámbrica de NetBox según el modelo de AP."""
    return MODEL_TO_WIFI_TYPE.get(model_code, "ieee802.11ax")


def resolve_ssids_for_mac(
    mac: str,
    ap_groups: List[Dict[str, Any]],
    wlans: List[Dict[str, Any]],
) -> Set[str]:
    """Determina los SSIDs que difunde un AP según su pertenencia a AP Groups de UniFi."""
    norm_mac = mac.strip().lower()
    matching_group_ids: Set[str] = set()

    for grp in ap_groups:
        dev_macs = [m.lower() for m in grp.get("device_macs", [])]
        if norm_mac in dev_macs:
            matching_group_ids.add(grp["id"])

    ssids: Set[str] = set()
    for w in wlans:
        w_ap_groups = set(w.get("ap_group_ids", []))
        if w_ap_groups & matching_group_ids:
            # Normalizar nombre de SSID eliminando espacios finales si existen
            ssids.add(w["name"].strip())

    # Fallback: si por algún motivo no hay grupo específico, asignar corporativo e invitados estándar
    if not ssids:
        ssids = {"EDISON_NEXT", "INVITADOS_EDISON_NEXT"}

    return ssids


def ensure_wireless_groups(client: NetBoxClient, dry_run: bool = True) -> Dict[str, int]:
    """Crea o concilia los Wireless LAN Groups en NetBox."""
    print("Verificando Wireless LAN Groups en NetBox...")
    existing = client.get_all("wireless/wireless-lan-groups")
    groups_by_slug: Dict[str, int] = {g["slug"]: g["id"] for g in existing}

    for slug, info in WIRELESS_LAN_GROUPS.items():
        if slug in groups_by_slug:
            print(f"  [EXISTS] Grupo '{info['name']}' presente (ID: {groups_by_slug[slug]})")
        else:
            payload = {
                "name": info["name"],
                "slug": info["slug"],
                "description": info["description"],
            }
            if dry_run:
                print(f"  [DRY-RUN] Crearía Wireless LAN Group: {payload}")
                groups_by_slug[slug] = 99901
            else:
                created = client.post("wireless/wireless-lan-groups", payload)
                groups_by_slug[slug] = created["id"]
                print(f"  [CREATED] Wireless LAN Group '{info['name']}' creado con ID {created['id']}")

    return groups_by_slug


def ensure_wireless_lans(
    client: NetBoxClient,
    group_ids_by_slug: Dict[str, int],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Crea o concilia los Wireless LANs (SSIDs) en NetBox."""
    print("\nVerificando Wireless LANs (SSIDs) en NetBox...")
    existing = client.get_all("wireless/wireless-lans")
    wl_by_ssid: Dict[str, int] = {w["ssid"]: w["id"] for w in existing}

    for wl in WIRELESS_LANS:
        ssid = wl["ssid"]
        group_id = group_ids_by_slug.get(wl["group_slug"])
        if ssid in wl_by_ssid:
            print(f"  [EXISTS] SSID '{ssid}' presente (ID: {wl_by_ssid[ssid]})")
        else:
            payload = {
                "ssid": ssid,
                "group": group_id,
                "status": wl["status"],
                "auth_type": wl["auth_type"],
                "auth_cipher": wl["auth_cipher"],
                "description": wl["description"],
            }
            if dry_run:
                print(f"  [DRY-RUN] Crearía Wireless LAN: {ssid} (Auth: {wl['auth_type']}, Grupo: {wl['group_slug']})")
                wl_by_ssid[ssid] = 88801
            else:
                created = client.post("wireless/wireless-lans", payload)
                wl_by_ssid[ssid] = created["id"]
                print(f"  [CREATED] Wireless LAN '{ssid}' creado con ID {created['id']}")

    return wl_by_ssid


def run_ingest(
    ap_input_file: str = "inputs/unifi_access_points.json",
    apg_input_file: str = "inputs/unifi_ap_groups.json",
    wlans_input_file: str = "inputs/unifi_wlans.json",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Ejecuta la ingesta e interconexión de Wireless LANs con los Access Points."""
    mode_str = "DRY-RUN" if dry_run else "REAL"
    print(f"\n=======================================================")
    print(f"  INGESTA DE WIRELESS LANS Y SSIDS EN NETBOX [{mode_str}]")
    print(f"=======================================================\n")

    client = NetBoxClient()

    # Cargar archivos de insumos
    with open(ap_input_file, "r", encoding="utf-8") as f:
        aps = json.load(f)

    with open(apg_input_file, "r", encoding="utf-8") as f:
        apg_raw = json.load(f)
        ap_groups = apg_raw.get("ap_groups", [])

    with open(wlans_input_file, "r", encoding="utf-8") as f:
        wlans = json.load(f)

    # 1. Crear / Conciliar Grupos
    group_ids = ensure_wireless_groups(client, dry_run=dry_run)

    # 2. Crear / Conciliar SSIDs
    wlan_ids = ensure_wireless_lans(client, group_ids, dry_run=dry_run)

    # 3. Conciliar Interfaces Inalámbricas 'wlan0' en los APs de NetBox
    print("\nConciliando interfaces inalámbricas 'wlan0' en los 56 Access Points...")
    nb_devices = client.get_all("dcim/devices", params={"role": "wireless-ap"})
    devices_by_name = {d["name"]: d for d in nb_devices}

    stats = {
        "groups_created": 0,
        "wlans_created": 0,
        "ap_interfaces_created": 0,
        "ap_interfaces_updated": 0,
        "ap_interfaces_existing": 0,
        "errors": [],
    }

    results = []

    for idx, ap in enumerate(aps, 1):
        name = ap["name"].strip()
        mac = ap["mac"]
        model = ap["model"]

        dev_obj = devices_by_name.get(name)
        if not dev_obj:
            print(f"[WARN] Dispositivo '{name}' no encontrado en NetBox.")
            continue

        dev_id = dev_obj["id"]
        wifi_iface_type = get_wifi_interface_type(model)

        # Resolver SSIDs para este AP
        active_ssids = resolve_ssids_for_mac(mac, ap_groups, wlans)
        active_wlan_ids = sorted([wlan_ids[s] for s in active_ssids if s in wlan_ids])

        print(f"[{idx:02d}/56] {name} (ID: {dev_id})")
        print(f"  Estándar WiFi: {wifi_iface_type} | SSIDs ({len(active_ssids)}): {sorted(list(active_ssids))}")

        if dry_run:
            print(f"  [DRY-RUN] Crearía/Actualizaría interfaz 'wlan0' con Wireless LAN IDs {active_wlan_ids}")
            stats["ap_interfaces_created"] += 1
        else:
            dev_ifaces = client.get_all("dcim/interfaces", params={"device_id": dev_id})
            wlan0 = next((i for i in dev_ifaces if i["name"] == "wlan0"), None)

            if not wlan0:
                payload = {
                    "device": dev_id,
                    "name": "wlan0",
                    "type": wifi_iface_type,
                    "enabled": True,
                    "wireless_lans": active_wlan_ids,
                    "description": "Radios WiFi 2.4/5GHz",
                }
                try:
                    created_iface = client.post("dcim/interfaces", payload)
                    stats["ap_interfaces_created"] += 1
                    print(f"  [CREATED] Interfaz 'wlan0' creada con ID: {created_iface['id']}")
                except Exception as e:
                    err = f"Error creando wlan0 en {name}: {e}"
                    print(f"  [ERROR] {err}")
                    stats["errors"].append({"ap": name, "error": str(e)})
            else:
                current_wlans = sorted([w["id"] for w in wlan0.get("wireless_lans", [])])
                current_type = wlan0.get("type", {}).get("value")
                needs_patch = (current_wlans != active_wlan_ids) or (current_type != wifi_iface_type)

                if needs_patch:
                    patch_data = {
                        "wireless_lans": active_wlan_ids,
                        "type": wifi_iface_type,
                    }
                    try:
                        client.patch("dcim/interfaces", wlan0["id"], patch_data)
                        stats["ap_interfaces_updated"] += 1
                        print(f"  [UPDATED] Interfaz 'wlan0' actualizada con SSIDs {active_wlan_ids}")
                    except Exception as e:
                        print(f"  [ERROR] Error actualizando wlan0 en {name}: {e}")
                else:
                    stats["ap_interfaces_existing"] += 1
                    print(f"  [EXISTS] Interfaz 'wlan0' ya configurada correctamente")

        results.append({
            "name": name,
            "mac": mac,
            "wifi_type": wifi_iface_type,
            "ssids": sorted(list(active_ssids)),
        })

    # Guardar resumen
    summary_path = "inputs/wireless_ingest_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "mode": mode_str,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stats": stats,
                "details": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print("\n=======================================================")
    print(f"  RESUMEN FINAL DE INGESTA DE WIRELESS [{mode_str}]")
    print(f"=======================================================")
    print(f"- Wireless LAN Groups configurados: {len(WIRELESS_LAN_GROUPS)}")
    print(f"- Wireless LANs (SSIDs) configurados: {len(WIRELESS_LANS)}")
    print(f"- Interfaces wlan0 creadas: {stats['ap_interfaces_created']}")
    print(f"- Interfaces wlan0 actualizadas: {stats['ap_interfaces_updated']}")
    print(f"- Interfaces wlan0 preexistentes: {stats['ap_interfaces_existing']}")
    print(f"- Total errores: {len(stats['errors'])}")
    print(f"- Resumen guardado en: {summary_path}\n")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta idempotente de Wireless LANs en NetBox")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Ejecutar en modo simulación")
    parser.add_argument("--real", action="store_true", default=False, help="Ejecutar en modo real contra NetBox")

    args = parser.parse_args()
    is_dry_run = not args.real
    run_ingest(dry_run=is_dry_run)


if __name__ == "__main__":
    main()
