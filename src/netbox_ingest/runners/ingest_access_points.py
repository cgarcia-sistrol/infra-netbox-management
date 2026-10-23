#!/usr/bin/env python3
"""Script de ingesta idempotente para Access Points UniFi en NetBox.

Crea y concilia:
- DeviceType faltante ('U6 Pro') bajo el fabricante Ubiquiti.
- 56 Access Points vinculados a su sede en NetBox (según IPAM y resolución de sedes).
- Interfaz cableada 'eth0' con dirección MAC registrada.
- Dirección IPv4 con su máscara CIDR exacta, asignada a 'eth0' y como Primary IPv4.
"""

import argparse
import ipaddress
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from netbox_ingest.client import NetBoxClient

# Mapeo de códigos de hardware UniFi a especificaciones en NetBox
MODEL_MAPPING: Dict[str, Dict[str, Any]] = {
    "UALR6v2": {
        "model": "U6 LR",
        "part_number": "U6-LR",
        "slug": "u6-lr",
        "iface_type": "1000base-t",
    },
    "UKPW": {
        "model": "U7 Outdoor",
        "part_number": "U7-Outdoor",
        "slug": "u7-outdoor",
        "iface_type": "2.5gbase-t",
    },
    "U7PRO": {
        "model": "U7 Pro",
        "part_number": "U7-Pro",
        "slug": "u7-pro",
        "iface_type": "2.5gbase-t",
    },
    "U7PG2": {
        "model": "UniFi AP-AC-Pro",
        "part_number": "UAP-AC-Pro",
        "slug": "unifi-ap-ac-pro",
        "iface_type": "1000base-t",
    },
    "U6M": {
        "model": "U6 Mesh",
        "part_number": "U6-Mesh",
        "slug": "u6-mesh",
        "iface_type": "1000base-t",
    },
    "U7LR": {
        "model": "UniFi AP-AC-LR",
        "part_number": "UAP-AC-LR",
        "slug": "unifi-ap-ac-lr",
        "iface_type": "1000base-t",
    },
    "UAP6MP": {
        "model": "U6 Pro",
        "part_number": "U6-Pro",
        "slug": "u6-pro",
        "iface_type": "1000base-t",
    },
}

# Reglas manuales de sede para casos especiales (stock, lab, IPs legacy)
SPECIAL_SITE_RULES: Dict[str, str] = {
    "ALM-01": "Delegación Almería",
}


def resolve_site_and_mask(
    name: str,
    ip_str: str,
    prefixes: List[Tuple[ipaddress.IPv4Network, str, str]],
) -> Tuple[Optional[str], Optional[int], str]:
    """Determina el nombre de sede en NetBox, la longitud de máscara CIDR y el estado deseado.
    
    Returns:
        (site_name, prefix_len, device_status)
    """
    # APs en stock / disponibles: asignar a JESP con status 'staged' según decisión del usuario
    if name.startswith("DISPONIBLE"):
        return ("JESP", 25 if ip_str.startswith("10.150.17.") or ip_str.startswith("10.152.17.") else 24, "staged")

    if name in SPECIAL_SITE_RULES:
        # Almería legacy IP (10.101.194.30)
        return (SPECIAL_SITE_RULES[name], 24, "offline")

    best_len = -1
    best_site: Optional[str] = None

    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for net, site_name, _ in prefixes:
            if ip_obj in net:
                if net.prefixlen > best_len:
                    best_len = net.prefixlen
                    best_site = site_name
    except ValueError:
        return (None, None, "offline")

    return (best_site, best_len if best_len > 0 else 24, "active")


def ensure_device_types(client: NetBoxClient, dry_run: bool = True) -> Dict[str, Dict[str, Any]]:
    """Verifica la existencia de los tipos de dispositivo de Ubiquiti y da de alta los faltantes."""
    print("Verificando DeviceTypes de Ubiquiti en NetBox...")
    existing = client.get_all("dcim/device-types", params={"manufacturer_id": 3})
    dt_by_model: Dict[str, Dict[str, Any]] = {dt["model"]: dt for dt in existing}

    for code, spec in MODEL_MAPPING.items():
        m_name = spec["model"]
        if m_name not in dt_by_model:
            print(f"[MISSING] DeviceType '{m_name}' (Slug: {spec['slug']}) no existe.")
            payload = {
                "manufacturer": 3,  # Ubiquiti
                "model": m_name,
                "slug": spec["slug"],
                "part_number": spec["part_number"],
                "u_height": 0.0,
                "is_full_depth": False,
                "description": f"Ubiquiti {m_name} Access Point",
            }
            if dry_run:
                print(f"  [DRY-RUN] Crearía DeviceType: {payload}")
                dt_by_model[m_name] = {"id": 99999, "model": m_name}
            else:
                created = client.post("dcim/device-types", payload)
                dt_by_model[m_name] = created
                print(f"  [CREATED] DeviceType '{m_name}' creado con ID {created['id']}")
        else:
            # print(f"  [OK] DeviceType '{m_name}' presente (ID: {dt_by_model[m_name]['id']})")
            pass

    return dt_by_model


def run_ingest(
    input_file: str = "inputs/unifi_access_points.json",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Ejecuta la ingesta idempotente de APs."""
    mode_str = "DRY-RUN" if dry_run else "REAL"
    print(f"\n=======================================================")
    print(f"  INGESTA DE ACCESS POINTS UNIFI EN NETBOX [{mode_str}]")
    print(f"=======================================================\n")

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Archivo de entrada no encontrado: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        unifi_devs: List[Dict[str, Any]] = json.load(f)

    print(f"Total puntos de acceso a procesar: {len(unifi_devs)}")

    client = NetBoxClient()

    # 1. DeviceTypes
    device_types = ensure_device_types(client, dry_run=dry_run)

    # 2. Sites y Prefijos
    print("\nCargando sedes y prefijos IPAM de NetBox...")
    sites = client.get_all("dcim/sites")
    sites_by_name = {s["name"]: s for s in sites}
    sites_by_id = {s["id"]: s["name"] for s in sites}

    prefixes_raw = client.get_all("ipam/prefixes")
    prefixes: List[Tuple[ipaddress.IPv4Network, str, str]] = []

    # Extraer nombre de sede del prefijo (campo site o description)
    for p in prefixes_raw:
        try:
            p_net = ipaddress.ip_network(p["prefix"])
        except ValueError:
            continue
        p_site = p.get("site")
        site_name = None
        if p_site:
            site_name = p_site.get("name") or sites_by_id.get(p_site.get("id"))
        
        # Si el prefijo no tiene site_id explícito, extraer de la descripción
        if not site_name and p.get("description"):
            desc = p["description"]
            if "Contenedor Sede:" in desc:
                site_name = desc.split("Contenedor Sede:")[1].split("(")[0].strip()
            elif "Subred LAN_Gestion_Infra_" in desc:
                raw_slug = desc.split("Subred LAN_Gestion_Infra_")[1].split("(")[0].strip().lower().replace("_", "-")
                for s in sites:
                    if s["slug"] == raw_slug:
                        site_name = s["name"]
                        break
            elif "Subred LAN_OT_Industrial_" in desc:
                raw_slug = desc.split("Subred LAN_OT_Industrial_")[1].split("(")[0].strip().lower().replace("_", "-")
                for s in sites:
                    if s["slug"] == raw_slug:
                        site_name = s["name"]
                        break

        if site_name and site_name in sites_by_name:
            prefixes.append((p_net, site_name, p.get("description", "")))

    print(f"Prefijos con sede resuelta: {len(prefixes)}")

    # 3. Dispositivos existentes
    print("Cargando dispositivos e interfaces existentes...")
    existing_devices_list = client.get_all("dcim/devices", params={"role": "wireless-ap"})
    devices_by_name = {d["name"]: d for d in existing_devices_list}

    # 4. IPs existentes en NetBox
    existing_ips_list = client.get_all("ipam/ip-addresses")
    ip_by_raw: Dict[str, Dict[str, Any]] = {}
    for ip_obj in existing_ips_list:
        raw = ip_obj["address"].split("/")[0]
        ip_by_raw[raw] = ip_obj

    role_id = 4  # Wireless Access Point

    stats = {
        "total_aps": len(unifi_devs),
        "devices_created": 0,
        "devices_existing": 0,
        "interfaces_created": 0,
        "interfaces_existing": 0,
        "ips_created": 0,
        "ips_updated": 0,
        "primary_ips_assigned": 0,
        "errors": [],
    }

    results_detail = []

    for idx, ap in enumerate(unifi_devs, 1):
        name = ap.get("name", "").strip()
        mac = ap.get("mac", "").strip().upper()
        ip_raw = ap.get("ip", "").strip()
        model_code = ap.get("model", "").strip()
        status_unifi = ap.get("status", "").strip().lower()
        firmware = ap.get("firmware", "")
        uptime = ap.get("uptime", "N/A")

        model_spec = MODEL_MAPPING.get(model_code)
        if not model_spec:
            err = f"Modelo desconocido '{model_code}' para AP {name}"
            print(f"[ERROR] {err}")
            stats["errors"].append({"ap": name, "error": err})
            continue

        model_name = model_spec["model"]
        dt_obj = device_types.get(model_name)
        dt_id = dt_obj["id"] if dt_obj else None

        # Resolver sede y máscara
        site_name, mask_len, status_derived = resolve_site_and_mask(name, ip_raw, prefixes)
        if not site_name or site_name not in sites_by_name:
            err = f"No se pudo resolver la sede para IP {ip_raw} (AP: {name})"
            print(f"[ERROR] {err}")
            stats["errors"].append({"ap": name, "error": err})
            continue

        site_obj = sites_by_name[site_name]
        site_id = site_obj["id"]

        device_status = status_derived if status_unifi != "online" else "active"
        if name.startswith("DISPONIBLE"):
            device_status = "staged"

        ip_cidr = f"{ip_raw}/{mask_len}"

        print(f"[{idx:02d}/{len(unifi_devs)}] {name}")
        print(f"  Hardware: {model_name} (Code: {model_code}) | MAC: {mac}")
        print(f"  Sede: {site_name} (ID: {site_id}) | Estado: {device_status}")
        print(f"  IP: {ip_cidr}")

        device_id = None
        if name in devices_by_name:
            dev_obj = devices_by_name[name]
            device_id = dev_obj["id"]
            stats["devices_existing"] += 1
            print(f"  [EXISTS] Dispositivo ya existe en NetBox (ID: {device_id})")
        else:
            dev_payload = {
                "name": name,
                "device_type": dt_id,
                "role": role_id,
                "site": site_id,
                "status": device_status,
                "serial": mac,
                "comments": f"Adoptado en UniFi Network.\nModelo UniFi: {model_code}\nFirmware: {firmware}\nUptime al importar: {uptime}",
            }
            if dry_run:
                print(f"  [DRY-RUN] Crearía Dispositivo: {dev_payload['name']} en {site_name}")
                stats["devices_created"] += 1
                device_id = 88800 + idx
            else:
                try:
                    dev_created = client.post("dcim/devices", dev_payload)
                    device_id = dev_created["id"]
                    devices_by_name[name] = dev_created
                    stats["devices_created"] += 1
                    print(f"  [CREATED] Dispositivo creado con ID: {device_id}")
                except Exception as e:
                    err = f"Error creando dispositivo {name}: {e}"
                    print(f"  [ERROR] {err}")
                    stats["errors"].append({"ap": name, "error": str(e)})
                    continue

        # Conciliar interfaz 'eth0'
        iface_id = None
        if not dry_run and device_id:
            dev_ifaces = client.get_all("dcim/interfaces", params={"device_id": device_id})
            eth0 = next((i for i in dev_ifaces if i["name"] == "eth0"), None)
            if eth0:
                iface_id = eth0["id"]
                stats["interfaces_existing"] += 1
                if eth0.get("mac_address") != mac:
                    client.patch("dcim/interfaces", iface_id, {"mac_address": mac})
                    print(f"  [UPDATED] MAC de eth0 actualizada a {mac}")
            else:
                iface_payload = {
                    "device": device_id,
                    "name": "eth0",
                    "type": model_spec["iface_type"],
                    "mac_address": mac,
                    "enabled": True,
                    "description": "Uplink LAN PoE",
                }
                try:
                    created_iface = client.post("dcim/interfaces", iface_payload)
                    iface_id = created_iface["id"]
                    stats["interfaces_created"] += 1
                    print(f"  [CREATED] Interfaz eth0 creada con ID: {iface_id}")
                except Exception as e:
                    err = f"Error creando interfaz eth0: {e}"
                    print(f"  [ERROR] {err}")
                    stats["errors"].append({"ap": name, "error": str(e)})
        else:
            stats["interfaces_created"] += 1
            iface_id = 77700 + idx
            print(f"  [DRY-RUN] Crearía/Verificaría interfaz eth0 ({model_spec['iface_type']}, MAC: {mac})")

        # Conciliar IP Address
        ip_obj_id = None
        if dry_run:
            stats["ips_created"] += 1
            stats["primary_ips_assigned"] += 1
            print(f"  [DRY-RUN] Crearía/Asignaría IP {ip_cidr} a interfaz eth0 y como primary_ip4")
        else:
            existing_ip = ip_by_raw.get(ip_raw)
            if existing_ip:
                ip_obj_id = existing_ip["id"]
                patch_ip = {
                    "address": ip_cidr,
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": iface_id,
                    "description": f"IP de gestión - AP {name}",
                }
                try:
                    client.patch("ipam/ip-addresses", ip_obj_id, patch_ip)
                    stats["ips_updated"] += 1
                    print(f"  [OK] IP {ip_cidr} existente asociada a eth0 (ID: {ip_obj_id})")
                except Exception as e:
                    print(f"  [WARN] Error actualizando IP {ip_cidr}: {e}")
            else:
                new_ip_payload = {
                    "address": ip_cidr,
                    "status": "active" if device_status == "active" else "reserved",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": iface_id,
                    "description": f"IP de gestión - AP {name}",
                }
                try:
                    res_ip = client.post("ipam/ip-addresses", new_ip_payload)
                    ip_obj_id = res_ip["id"]
                    ip_by_raw[ip_raw] = res_ip
                    stats["ips_created"] += 1
                    print(f"  [CREATED] IP {ip_cidr} creada y asignada a eth0 (ID: {ip_obj_id})")
                except Exception as e:
                    err = f"Error creando IP {ip_cidr}: {e}"
                    print(f"  [ERROR] {err}")
                    stats["errors"].append({"ap": name, "error": str(e)})

            # Asignar Primary IP al dispositivo
            if ip_obj_id and device_id:
                try:
                    client.patch("dcim/devices", device_id, {"primary_ip4": ip_obj_id})
                    stats["primary_ips_assigned"] += 1
                    print(f"  [OK] Primary IP4 asignada al AP {name}")
                except Exception as e:
                    print(f"  [WARN] Error asignando primary_ip4: {e}")

        results_detail.append({
            "name": name,
            "mac": mac,
            "model": model_name,
            "site": site_name,
            "ip": ip_cidr,
            "status": device_status,
        })

    # Guardar resumen en archivo JSON
    summary_path = "inputs/access_points_ingest_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "mode": mode_str,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stats": stats,
                "devices": results_detail,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print("\n=======================================================")
    print(f"  RESUMEN FINAL DE INGESTA [{mode_str}]")
    print(f"=======================================================")
    print(f"- Total APs analizados: {stats['total_aps']}")
    print(f"- Dispositivos a crear/creados: {stats['devices_created']}")
    print(f"- Dispositivos preexistentes: {stats['devices_existing']}")
    print(f"- Interfaces eth0 a crear/creadas: {stats['interfaces_created']}")
    print(f"- IPs creadas: {stats['ips_created']}")
    print(f"- IPs actualizadas/asociadas: {stats['ips_updated']}")
    print(f"- Primary IPs asignadas: {stats['primary_ips_assigned']}")
    print(f"- Total errores: {len(stats['errors'])}")
    print(f"- Detalle guardado en: {summary_path}\n")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta idempotente de APs UniFi en NetBox")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Ejecutar en modo simulación (sin mutar NetBox)")
    parser.add_argument("--real", action="store_true", default=False, help="Ejecutar en modo real contra la API de NetBox")
    parser.add_argument("--input", default="inputs/unifi_access_points.json", help="Ruta al archivo JSON de APs UniFi")

    args = parser.parse_args()

    # Por defecto dry-run a menos que se especifique --real
    is_dry_run = not args.real
    run_ingest(input_file=args.input, dry_run=is_dry_run)


if __name__ == "__main__":
    main()
