#!/usr/bin/env python3
"""Script de importación idempotente de interfaces y direcciones IP en NetBox.

Lee el catálogo en inputs/catalogo_interfaces_firewalls.json, filtra las interfaces de ruido
(VLANs internas de FortiLink VIDs 1 y 4088-4093, daemons de FortiOS), crea la jerarquía
de LAG fortilink, asocia puertos físicos miembros (a/b o port11/12), crea subinterfaces VLAN
con parent fortilink, crea túneles VPN IPsec y asocia/crea las direcciones IP correspondientes
(gateways de VLANs, IPs WAN y asignación de primary_ip4).
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from netbox_ingest.client import NetBoxClient

CATALOG_PATH = "/home/carlos/projects-ag/infra-netbox-management/inputs/catalogo_interfaces_firewalls.json"
SUMMARY_OUTPUT = "/home/carlos/projects-ag/infra-netbox-management/inputs/firewall_interfaces_ingest_summary.json"

EXCLUDED_VIDS = {1, 4088, 4089, 4090, 4091, 4092, 4093}
EXCLUDED_NAMES = {
    "_default",
    "nac_segment",
    "onboarding",
    "voice",
    "video",
    "quarantine",
    "rspan",
    "naf.root",
    "l2t.root",
    "ssl.root",
    "modem",
}


def should_import_interface(iface: Dict[str, Any]) -> bool:
    """Filtra interfaces internas de FortiLink y daemons ruidosos."""
    name = iface["name"]
    vid = iface.get("vlan_id")
    cat = iface.get("category")

    if vid in EXCLUDED_VIDS or name in EXCLUDED_NAMES:
        return False
    if name.endswith(".fortilink"):
        return False
    if cat == "physical":
        return False
    return True


def run_ingest(dry_run: bool = True) -> Dict[str, Any]:
    print(f"=== Iniciando Ingesta de Interfaces y Direcciones IP en NetBox [Modo: {'DRY-RUN' if dry_run else 'REAL'}] ===")
    if not os.path.exists(CATALOG_PATH):
        raise FileNotFoundError(f"Catálogo no encontrado en {CATALOG_PATH}")

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog_data = json.load(f)

    devices = catalog_data.get("devices", [])
    print(f"Total firewalls en catálogo: {len(devices)}")

    nb = NetBoxClient()

    print("Cargando inventario actual de IPAM y DCIM en NetBox...")
    all_nb_ips = nb.get_all("ipam/ip-addresses")
    ip_by_cidr: Dict[str, Dict[str, Any]] = {}
    ip_by_raw: Dict[str, List[Dict[str, Any]]] = {}

    for ip_obj in all_nb_ips:
        cidr = ip_obj["address"]
        raw = cidr.split("/")[0]
        ip_by_cidr[cidr] = ip_obj
        ip_by_raw.setdefault(raw, []).append(ip_obj)

    stats = {
        "devices_processed": 0,
        "lags_created": 0,
        "lag_members_updated": 0,
        "vlan_subinterfaces_created": 0,
        "vpn_tunnels_created": 0,
        "loopbacks_created": 0,
        "ips_associated": 0,
        "ips_created_and_associated": 0,
        "primary_ips_assigned": 0,
        "errors": [],
    }

    for dev in devices:
        dev_name = dev.get("hostname") or dev.get("alias")
        netbox_id = dev.get("netbox_device_id")
        site_name = dev.get("netbox_site")

        if not netbox_id:
            print(f"⚠️ Omitiendo {dev_name}: no emparejado con ID de NetBox.")
            continue

        stats["devices_processed"] += 1
        print(f"\n--- [{stats['devices_processed']}/{len(devices)}] Procesando {dev_name} (ID: {netbox_id}, Sede: {site_name}) ---")

        # 1. Consultar interfaces existentes en este dispositivo
        existing_ifaces_list = nb.get_all("dcim/interfaces", params={"device_id": netbox_id})
        existing_ifaces = {i["name"]: i for i in existing_ifaces_list}

        # 2. Gestionar interfaz agregada FortiLink
        fortilink_iface = None
        for iface in dev.get("interfaces", []):
            if iface["name"] == "fortilink" or iface["category"] == "aggregate_fortilink":
                fortilink_iface = iface
                break

        fortilink_id = None
        if fortilink_iface:
            if "fortilink" in existing_ifaces:
                fortilink_id = existing_ifaces["fortilink"]["id"]
            else:
                payload = {
                    "device": netbox_id,
                    "name": "fortilink",
                    "type": "lag",
                    "description": "Troncal FortiLink LACP",
                    "enabled": True,
                }
                if dry_run:
                    print(f"  [DRY-RUN] Crearía interfaz LAG 'fortilink' en device {netbox_id}")
                    fortilink_id = 999999
                    stats["lags_created"] += 1
                else:
                    try:
                        res = nb.post("dcim/interfaces", data=payload)
                        fortilink_id = res["id"]
                        existing_ifaces["fortilink"] = res
                        stats["lags_created"] += 1
                        print(f"  [OK] Creada interfaz LAG 'fortilink' (ID: {fortilink_id})")
                    except Exception as e:
                        print(f"  [ERR] Creando fortilink: {e}")
                        stats["errors"].append(f"{dev_name} fortilink: {e}")

            # Vincular miembros LAG físicos (ej. a, b o port11, port12)
            members = fortilink_iface.get("members") or []
            if not members and "FGT60" in dev_name.upper():
                members = ["a", "b"]

            for member_name in members:
                if member_name in existing_ifaces:
                    m_obj = existing_ifaces[member_name]
                    curr_lag = m_obj.get("lag")
                    curr_lag_id = curr_lag.get("id") if isinstance(curr_lag, dict) else curr_lag
                    if curr_lag_id != fortilink_id and fortilink_id:
                        if dry_run:
                            print(f"  [DRY-RUN] Asociaría puerto físico '{member_name}' (ID: {m_obj['id']}) a LAG fortilink")
                            stats["lag_members_updated"] += 1
                        else:
                            try:
                                nb.patch("dcim/interfaces", m_obj["id"], {"lag": fortilink_id})
                                stats["lag_members_updated"] += 1
                                print(f"  [OK] Puerto físico '{member_name}' asignado a LAG fortilink")
                            except Exception as e:
                                print(f"  [ERR] Asociando {member_name} a LAG: {e}")
                                stats["errors"].append(f"{dev_name} lag member {member_name}: {e}")

        # 3. Crear Subinterfaces VLAN y Túneles VPN
        created_or_existing_ifaces: Dict[str, int] = {}
        for name, obj in existing_ifaces.items():
            created_or_existing_ifaces[name] = obj["id"]

        for iface in dev.get("interfaces", []):
            if not should_import_interface(iface):
                continue
            if iface["name"] == "fortilink" or iface["category"] == "aggregate_fortilink":
                continue

            iface_name = iface["name"]
            cat = iface["category"]
            vlan_id = iface.get("vlan_id")
            alias = iface.get("alias") or ""
            nb_vlan_id = iface.get("netbox_vlan_id")

            if iface_name in existing_ifaces:
                created_or_existing_ifaces[iface_name] = existing_ifaces[iface_name]["id"]
                continue

            # Mapear tipos válidos de NetBox
            netbox_type = "virtual"
            if cat == "hard_switch":
                netbox_type = "bridge"
            elif cat == "aggregate_fortilink":
                netbox_type = "lag"

            payload = {
                "device": netbox_id,
                "name": iface_name,
                "type": netbox_type,
                "enabled": iface.get("enabled", True),
                "label": alias[:64] if alias else "",
                "description": f"{alias} - {dev_name}"[:200] if alias else "",
            }

            if cat == "vlan_subinterface":
                payload["parent"] = fortilink_id
                payload["mode"] = "tagged"
                if nb_vlan_id:
                    payload["tagged_vlans"] = [nb_vlan_id]
                stats_key = "vlan_subinterfaces_created"
            elif cat == "vpn_tunnel":
                stats_key = "vpn_tunnels_created"
            elif cat == "loopback":
                stats_key = "loopbacks_created"
            else:
                stats_key = "vlan_subinterfaces_created"

            if dry_run:
                print(f"  [DRY-RUN] Crearía {cat} '{iface_name}' (type: {netbox_type}, alias: {alias})")
                stats[stats_key] += 1
                created_or_existing_ifaces[iface_name] = 999000 + stats[stats_key]
            else:
                try:
                    res = nb.post("dcim/interfaces", data=payload)
                    iface_id = res["id"]
                    created_or_existing_ifaces[iface_name] = iface_id
                    existing_ifaces[iface_name] = res
                    stats[stats_key] += 1
                    print(f"  [OK] Creada {cat} '{iface_name}' (ID: {iface_id})")
                except Exception as e:
                    print(f"  [ERR] Creando interfaz {iface_name}: {e}")
                    stats["errors"].append(f"{dev_name} iface {iface_name}: {e}")

        # 4. Asociar / Crear Direcciones IP
        mgmt_ip_obj_id = None
        for iface in dev.get("interfaces", []):
            iface_name = iface["name"]
            ip_cidr = iface.get("ip_cidr")
            if not ip_cidr or ip_cidr.startswith("0.0.0.0"):
                continue

            if iface.get("vlan_id") in EXCLUDED_VIDS or iface_name in EXCLUDED_NAMES:
                continue
            if ip_cidr.startswith("10.255."):
                continue

            target_iface_id = created_or_existing_ifaces.get(iface_name)
            if not target_iface_id and iface_name in existing_ifaces:
                target_iface_id = existing_ifaces[iface_name]["id"]

            if not target_iface_id:
                continue

            raw_ip = ip_cidr.split("/")[0]

            existing_ip_obj = ip_by_cidr.get(ip_cidr)
            if not existing_ip_obj and raw_ip in ip_by_raw:
                existing_ip_obj = ip_by_raw[raw_ip][0]

            alias_str = iface.get("alias") or iface_name

            if existing_ip_obj:
                ip_id = existing_ip_obj["id"]
                curr_assigned = existing_ip_obj.get("assigned_object_id")
                if iface.get("vlan_id") == 80 or raw_ip == dev.get("ip"):
                    mgmt_ip_obj_id = ip_id

                if curr_assigned != target_iface_id:
                    patch_payload = {
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": target_iface_id,
                        "description": f"Gateway {alias_str} - {dev_name}"[:200],
                    }

                    if dry_run:
                        print(f"  [DRY-RUN] Asociaría IP preexistente {ip_cidr} (ID: {ip_id}) a interfaz '{iface_name}'")
                        stats["ips_associated"] += 1
                    else:
                        try:
                            nb.patch("ipam/ip-addresses", ip_id, patch_payload)
                            stats["ips_associated"] += 1
                            print(f"  [OK] IP {ip_cidr} asociada a '{iface_name}'")
                        except Exception as e:
                            print(f"  [ERR] Asociando IP {ip_cidr}: {e}")
                            stats["errors"].append(f"{dev_name} IP {ip_cidr}: {e}")
            else:
                new_ip_payload = {
                    "address": ip_cidr,
                    "status": "active",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": target_iface_id,
                    "description": f"{alias_str} - {dev_name}"[:200],
                }

                if dry_run:
                    print(f"  [DRY-RUN] Crearía y asociaría nueva IP {ip_cidr} a interfaz '{iface_name}'")
                    stats["ips_created_and_associated"] += 1
                else:
                    try:
                        res_ip = nb.post("ipam/ip-addresses", data=new_ip_payload)
                        new_id = res_ip["id"]
                        ip_by_cidr[ip_cidr] = res_ip
                        ip_by_raw.setdefault(raw_ip, []).append(res_ip)
                        stats["ips_created_and_associated"] += 1
                        print(f"  [OK] Creada y asociada nueva IP {ip_cidr} (ID: {new_id}) a '{iface_name}'")
                        if iface.get("vlan_id") == 80 or raw_ip == dev.get("ip"):
                            mgmt_ip_obj_id = new_id
                    except Exception as e:
                        print(f"  [ERR] Creando IP {ip_cidr}: {e}")
                        stats["errors"].append(f"{dev_name} new IP {ip_cidr}: {e}")

        # 5. Asignar Primary IP al dispositivo en NetBox
        if mgmt_ip_obj_id and not dry_run:
            try:
                nb.patch("dcim/devices", netbox_id, {"primary_ip4": mgmt_ip_obj_id})
                stats["primary_ips_assigned"] += 1
                print(f"  [OK] Asignada Primary IP4 al firewall {dev_name}")
            except Exception as e:
                print(f"  [ERR] Asignando primary_ip4: {e}")
        elif mgmt_ip_obj_id and dry_run:
            print(f"  [DRY-RUN] Asignaría Primary IP4 al firewall {dev_name}")
            stats["primary_ips_assigned"] += 1

    with open(SUMMARY_OUTPUT, "w", encoding="utf-8") as f:
        json.dump({
            "mode": "DRY-RUN" if dry_run else "REAL",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stats": stats
        }, f, indent=2, ensure_ascii=False)

    print("\n=== RESUMEN DE EJECUCIÓN ===")
    print(f"Modo: {'DRY-RUN (Simulación)' if dry_run else 'REAL (Ejecutado en NetBox)'}")
    print(f"- Firewalls procesados: {stats['devices_processed']}")
    print(f"- Troncales LAG fortilink a crear/creados: {stats['lags_created']}")
    print(f"- Puertos físicos asociados a fortilink: {stats['lag_members_updated']}")
    print(f"- Subinterfaces VLAN a crear/creadas: {stats['vlan_subinterfaces_created']}")
    print(f"- Túneles VPN IPsec a crear/creados: {stats['vpn_tunnels_created']}")
    print(f"- Interfaces Loopback a crear/creadas: {stats['loopbacks_created']}")
    print(f"- IPs preexistentes asociadas a interfaces: {stats['ips_associated']}")
    print(f"- Nuevas IPs creadas y asociadas: {stats['ips_created_and_associated']}")
    print(f"- Primary IPs asignadas a firewalls: {stats['primary_ips_assigned']}")
    print(f"- Total errores registrados: {len(stats['errors'])}")
    print(f"Resumen guardado en: {SUMMARY_OUTPUT}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingesta de interfaces y direcciones IP en NetBox")
    parser.add_argument("--execute", action="store_true", help="Ejecuta los cambios reales en NetBox (por defecto es dry-run)")
    args = parser.parse_args()

    is_dry_run = not args.execute
    run_ingest(dry_run=is_dry_run)


if __name__ == "__main__":
    main()
