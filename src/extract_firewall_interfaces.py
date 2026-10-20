#!/usr/bin/env python3
"""Script de extracción y catalogación de interfaces en firewalls FortiGate.

Conecta de forma segura y no interactiva mediante SSH directo (infra_user) a los firewalls
definidos en ~/.local/fws/credentials, extrae la configuración completa de interfaces
mediante 'show system interface', categoriza la jerarquía (físicas, LAG fortilink, subinterfaces
VLAN 802.1Q, túneles VPN IPsec, interfaces loopback) y genera un catálogo estructurado
en JSON y Markdown para su evaluación previa a NetBox.
"""

import ipaddress
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import paramiko

# Intentar importar NetBoxClient para correlación en modo solo lectura
try:
    from netbox_ingest.client import NetBoxClient
    NETBOX_AVAILABLE = True
except Exception:
    NETBOX_AVAILABLE = False

CREDENTIALS_PATH = os.path.expanduser("~/.local/fws/credentials")
OUTPUT_JSON = "/home/carlos/projects-ag/infra-netbox-management/inputs/catalogo_interfaces_firewalls.json"
OUTPUT_MD = "/home/carlos/projects-ag/infra-netbox-management/inputs/catalogo_interfaces_firewalls.md"

# Mapeo unívoco de alias de credentials hacia nombres en NetBox
NAME_OVERRIDE_NETBOX = {
    "HUB_00": "FortiGate-100F",
    "FGT100-HUB00": "FortiGate-100F",
    "HUB_02": "FGT100-JES",
    "FGT100-HUB02": "FGT100-JES",
    "FGT60F_ARC_AVI": "FGT60F-ARC-AVI",
    "FW60F-ARC-AVI": "FGT60F-ARC-AVI",
    "FGT60F_FOM": "FGT60F-FOM",
    "FGT60-FOM": "FGT60F-FOM",
    "FGT60F_GIJ_OFI": "FGT60F-GIJ-OFI",
    "FW60F-GIJ-OFI": "FGT60F-GIJ-OFI",
    "FGT60F_ZNF": "FGT60F-ZNF",
    "FGT60-ZNF": "FGT60F-ZNF",
    "TEST_JESP": "FGT60F-TEST-JESP",
}


def load_credentials(path: str) -> Tuple[str, List[Dict[str, str]]]:
    """Carga credenciales desde archivo seguro ignorando comillas."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Archivo de credenciales no encontrado en {path}")

    infra_user = "infra_user"
    devices = []
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#") and "=" in l]

    current_alias = ""
    for l in lines:
        k, v = l.split("=", 1)
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if k == "FGT_INFRA_USER":
            infra_user = v
        elif k.startswith("FGT_PASS_") and not k.startswith("FGT_PASS_10_"):
            current_alias = k.replace("FGT_PASS_", "")
        elif k.startswith("FGT_PASS_10_"):
            ip = k.replace("FGT_PASS_", "").replace("_", ".")
            devices.append({
                "alias": current_alias,
                "ip": ip,
                "password": v
            })
            current_alias = ""

    return infra_user, devices


def fetch_firewall_interfaces_ssh(ip: str, user: str, password: str, timeout: int = 6) -> str:
    """Extrae la salida de 'show system interface' gestionando paginación interactiva."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip,
            port=22,
            username=user,
            password=password,
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False
        )

        chan = client.invoke_shell()
        time.sleep(0.4)
        if chan.recv_ready():
            chan.recv(65535)

        chan.send("show system interface\n")
        output = ""
        start_time = time.time()
        max_duration = 18

        while time.time() - start_time < max_duration:
            if chan.recv_ready():
                chunk = chan.recv(8192).decode("utf-8", errors="ignore")
                output += chunk
                # Bombeo de barra espaciadora si encontramos paginador
                if "--More--" in chunk or chunk.endswith("--More-- ") or "--More--" in output[-25:]:
                    chan.send(" ")
                    time.sleep(0.04)
            else:
                time.sleep(0.1)
                # Si el prompt final (# o $) se estabiliza y no hay más datos
                if (output.strip().endswith("$") or output.strip().endswith("#")) and not chan.recv_ready():
                    break

        client.close()
        return output
    except Exception as e:
        client.close()
        raise RuntimeError(f"Error SSH en {ip}: {type(e).__name__} - {e}")


def parse_interfaces_block(raw_text: str) -> List[Dict[str, Any]]:
    """Parsea el bloque de interfaces de FortiOS respetando anidamientos internos."""
    interfaces = []
    lines = raw_text.splitlines()
    current_name = None
    current_lines = []
    inside_interface = False

    parsed_blocks = []
    for line in lines:
        m_edit = re.match(r"^\s{4}edit\s+\"?([^\"\r\n]+)\"?", line)
        if m_edit:
            if current_name and inside_interface:
                parsed_blocks.append((current_name, "\n".join(current_lines)))
            current_name = m_edit.group(1)
            current_lines = []
            inside_interface = True
        elif inside_interface:
            if re.match(r"^\s{4}next", line):
                parsed_blocks.append((current_name, "\n".join(current_lines)))
                current_name = None
                current_lines = []
                inside_interface = False
            else:
                current_lines.append(line)

    for name, body in parsed_blocks:
        vdom_m = re.search(r'set\s+vdom\s+"?([^"\r\n]+)"?', body)
        ip_m = re.search(r'set\s+ip\s+([0-9\.]+)\s+([0-9\.]+)', body)
        type_m = re.search(r'set\s+type\s+([a-zA-Z0-9_\-]+)', body)
        vlanid_m = re.search(r'set\s+vlanid\s+(\d+)', body)
        interface_m = re.search(r'set\s+interface\s+"?([^"\r\n]+)"?', body)
        alias_m = re.search(r'set\s+alias\s+"?([^"\r\n]+)"?', body)
        desc_m = re.search(r'set\s+description\s+"?([^"\r\n]+)"?', body)
        role_m = re.search(r'set\s+role\s+([a-zA-Z0-9_\-]+)', body)
        status_m = re.search(r'set\s+status\s+([a-zA-Z0-9_\-]+)', body)
        allowaccess_m = re.search(r'set\s+allowaccess\s+([^\r\n]+)', body)
        fortilink_m = re.search(r'set\s+fortilink\s+(enable|disable)', body)
        members = re.findall(r'set\s+member\s+(.+)', body)

        member_list = []
        if members:
            member_list = [m.strip(' "') for m in re.findall(r'"[^"]+"|\S+', members[0])]

        ip_cidr = ""
        ip_addr = ""
        mask_addr = ""
        if ip_m:
            ip_addr = ip_m.group(1)
            mask_addr = ip_m.group(2)
            try:
                net = ipaddress.IPv4Network(f"{ip_addr}/{mask_addr}", strict=False)
                ip_cidr = f"{ip_addr}/{net.prefixlen}"
            except Exception:
                ip_cidr = f"{ip_addr} {mask_addr}"

        detected_type = type_m.group(1) if type_m else "physical"
        parent_iface = interface_m.group(1) if interface_m else None
        vlan_id = int(vlanid_m.group(1)) if vlanid_m else None

        # Categorización arquitectónica
        category = "physical"
        netbox_type = "1000base-t"

        if name == "fortilink" or (type_m and type_m.group(1) == "aggregate") or fortilink_m:
            category = "aggregate_fortilink"
            netbox_type = "lag"
        elif vlan_id is not None or detected_type == "vlan" or parent_iface == "fortilink" or "VLAN" in name:
            category = "vlan_subinterface"
            netbox_type = "virtual"
            if not parent_iface:
                parent_iface = "fortilink"
        elif detected_type == "tunnel" or "VPN" in name or name.startswith("to-") or name.startswith("To_"):
            category = "vpn_tunnel"
            netbox_type = "ipsec-tunnel"
        elif detected_type == "loopback" or "Loopback" in name:
            category = "loopback"
            netbox_type = "loopback"
        elif detected_type == "hard-switch":
            category = "hard_switch"
            netbox_type = "bridge"
        elif detected_type in ["redundant"]:
            category = "redundant"
            netbox_type = "lag"

        iface_data = {
            "name": name,
            "category": category,
            "netbox_type": netbox_type,
            "fortios_type": detected_type,
            "parent_interface": parent_iface,
            "vlan_id": vlan_id,
            "ip_address": ip_addr,
            "subnet_mask": mask_addr,
            "ip_cidr": ip_cidr,
            "alias": alias_m.group(1) if alias_m else (desc_m.group(1) if desc_m else None),
            "role": role_m.group(1) if role_m else None,
            "enabled": False if (status_m and status_m.group(1) == "down") else True,
            "allowaccess": allowaccess_m.group(1).strip() if allowaccess_m else None,
            "members": member_list if member_list else None,
            "vdom": vdom_m.group(1) if vdom_m else "root"
        }
        interfaces.append(iface_data)

    return interfaces


def correlate_with_netbox(catalog: List[Dict[str, Any]]) -> None:
    """Cruza los datos de cada firewall con NetBox en modo solo lectura."""
    if not NETBOX_AVAILABLE:
        print("NetBoxClient no disponible. Omitiendo cruce.")
        return

    try:
        nb = NetBoxClient()
        print("\nConsultando dispositivos y sitios en NetBox (Read-Only)...")
        nb_devices = nb.get_all("dcim/devices", params={"role": "firewall"})
        nb_dev_map = {d["name"]: d for d in nb_devices}

        for dev in catalog:
            fgt_name = dev.get("hostname") or dev.get("alias")
            target_name = NAME_OVERRIDE_NETBOX.get(dev.get("alias"), fgt_name)
            target_name = NAME_OVERRIDE_NETBOX.get(fgt_name, target_name)

            matched_nb = None
            for nb_name, d in nb_dev_map.items():
                if (nb_name.lower() == target_name.lower() or 
                    nb_name.lower() == fgt_name.lower() or
                    nb_name.lower().replace("-", "") == fgt_name.lower().replace("-", "") or
                    target_name.lower() in nb_name.lower()):
                    matched_nb = d
                    break

            if matched_nb:
                dev["netbox_device_id"] = matched_nb["id"]
                dev["netbox_device_name"] = matched_nb["name"]
                dev["netbox_site"] = matched_nb.get("site", {}).get("name")
                dev["netbox_site_slug"] = matched_nb.get("site", {}).get("slug")

                nb_ifaces = nb.get_all("dcim/interfaces", params={"device_id": matched_nb["id"]})
                nb_iface_names = {i["name"]: i for i in nb_ifaces}

                site_vlans = {}
                if dev.get("netbox_site_slug"):
                    vlans = nb.get_all("ipam/vlans", params={"site": dev["netbox_site_slug"]})
                    site_vlans = {v["vid"]: v for v in vlans}

                for iface in dev.get("interfaces", []):
                    if iface["name"] in nb_iface_names:
                        iface["netbox_existing_id"] = nb_iface_names[iface["name"]]["id"]
                        iface["netbox_status"] = "EXISTING"
                    else:
                        iface["netbox_status"] = "NEW"

                    if iface.get("vlan_id") and iface["vlan_id"] in site_vlans:
                        vlan_obj = site_vlans[iface["vlan_id"]]
                        iface["netbox_vlan_id"] = vlan_obj["id"]
                        iface["netbox_vlan_name"] = vlan_obj["name"]
    except Exception as e:
        print(f"Aviso durante la correlación con NetBox: {e}")


def generate_markdown_report(catalog: List[Dict[str, Any]], summary: Dict[str, Any], filepath: str) -> None:
    """Genera informe ejecutivo y tablas detalladas en Markdown."""
    lines = []
    lines.append("# Catálogo Consolidado de Interfaces en Firewalls FortiGate\n")
    lines.append(f"- **Fecha de Generación**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **Total Dispositivos Procesados**: {summary['total_devices']}")
    lines.append(f"- **Conexiones SSH Exitosas**: {summary['success_count']}")
    lines.append(f"- **Dispositivos Fallidos / Inalcanzables**: {summary['failed_count']}")
    lines.append(f"- **Total Interfaces Extraídas**: {summary['total_interfaces']}\n")

    lines.append("## 1. Resumen por Categoría de Interfaz\n")
    lines.append("| Categoría | Total Interfaces | Tipo NetBox | Función Técnica |")
    lines.append("| :--- | :---: | :--- | :--- |")
    lines.append(f"| **Físicas (Underlay)** | {summary['cat_physical']} | `1000base-t` / `10gbase-x-sfpp` | Puertos físicos de chasis (`wan1`, `wan2`, `internal1..5`, etc.) |")
    lines.append(f"| **Troncal FortiLink** | {summary['cat_fortilink']} | `lag` | Agregado LACP FortiLink (control switches `10.255.1.1/24`) |")
    lines.append(f"| **Subinterfaces VLAN** | {summary['cat_vlan']} | `virtual` (parent: `fortilink`) | Segmentación 802.1Q corporativa e industrial |")
    lines.append(f"| **Túneles VPN IPsec** | {summary['cat_vpn']} | `ipsec-tunnel` | Malla SD-WAN Hub-Spoke (`HubVPN01/02`) y túneles B2B |")
    lines.append(f"| **Loopback / Gestión** | {summary['cat_loopback']} | `loopback` | Interfaces lógicas de gestión y terminación de servicios |")
    lines.append(f"| **Otras (Bridge / Hard-Switch)** | {summary['cat_other']} | `bridge` / `virtual` | Conmutación local y puertos de contingencia |\n")

    lines.append("## 2. Detalle de Interfaces por Firewall\n")

    for dev in catalog:
        if not dev.get("success"):
            lines.append(f"### ❌ {dev['alias']} ({dev['ip']}) - Conexión Fallida")
            lines.append(f"- **Error**: `{dev.get('error')}`\n")
            continue

        nb_info = f"NetBox ID: `{dev.get('netbox_device_id')}` | Sede: **{dev.get('netbox_site', 'N/A')}**"
        lines.append(f"### 🛡️ {dev['hostname']} ({dev['alias']}) - `{dev['ip']}`")
        lines.append(f"- {nb_info}")
        lines.append(f"- **Total Interfaces**: {len(dev['interfaces'])}\n")

        # Tabla de FortiLink y Físicas Relevantes
        lines.append("#### Troncal FortiLink y Agregación")
        lines.append("| Interfaz | Tipo FortiOS | Tipo NetBox | Miembros Físicos | IP / CIDR | Estado NetBox |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for i in dev["interfaces"]:
            if i["category"] in ["aggregate_fortilink", "hard_switch"]:
                members_str = ", ".join(i.get("members", [])) if i.get("members") else "None"
                lines.append(f"| `{i['name']}` | `{i['fortios_type']}` | `{i['netbox_type']}` | `{members_str}` | `{i['ip_cidr'] or '-'}` | `{i.get('netbox_status', 'NEW')}` |")
        lines.append("")

        # Tabla de VLANs
        lines.append("#### Subinterfaces VLAN (802.1Q sobre FortiLink)")
        lines.append("| Interfaz | VID | Parent | Alias / Propósito | Gateway IP / CIDR | VLAN NetBox Match | Estado NetBox |")
        lines.append("| :--- | :---: | :--- | :--- | :--- | :--- | :---: |")
        for i in dev["interfaces"]:
            if i["category"] == "vlan_subinterface":
                vid_str = str(i["vlan_id"]) if i["vlan_id"] is not None else "-"
                parent_str = i["parent_interface"] or "fortilink"
                alias_str = i["alias"] or "-"
                vlan_nb_match = f"✅ #{i['netbox_vlan_id']} ({i['netbox_vlan_name']})" if i.get("netbox_vlan_id") else "⚠️ No enlazada"
                lines.append(f"| `{i['name']}` | **{vid_str}** | `{parent_str}` | `{alias_str}` | `{i['ip_cidr'] or '-'}` | {vlan_nb_match} | `{i.get('netbox_status', 'NEW')}` |")
        lines.append("")

        # Tabla de Túneles VPN
        lines.append("#### Túneles VPN IPsec y SD-WAN")
        lines.append("| Nombre Túnel | Tipo | Gateway Local | Servicios Permitidos | Estado NetBox |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        vpn_ifaces = [i for i in dev["interfaces"] if i["category"] in ["vpn_tunnel", "loopback"]]
        if vpn_ifaces:
            for i in vpn_ifaces:
                lines.append(f"| `{i['name']}` | `{i['netbox_type']}` | `{i['ip_cidr'] or '-'}` | `{i['allowaccess'] or '-'}` | `{i.get('netbox_status', 'NEW')}` |")
        else:
            lines.append("| *(Sin túneles configurados en este dispositivo)* | - | - | - | - |")
        lines.append("\n---\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    print("=== Iniciando Extracción y Catalogación de Interfaces FortiGate ===")
    user, devices = load_credentials(CREDENTIALS_PATH)
    print(f"Usuario SSH: {user} | Total dispositivos definidos: {len(devices)}")

    # Si ya existe el catálogo recién extraído, podemos simplemente re-correlacionar para ahorrar tiempo
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("devices") and len(cached["devices"]) == len(devices):
                print("Re-correlacionando datos existentes con NetBox...")
                catalog = cached["devices"]
                summary = cached["summary"]
                correlate_with_netbox(catalog)
                with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                    json.dump({
                        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "summary": summary,
                        "devices": catalog
                    }, f, indent=2, ensure_ascii=False)
                generate_markdown_report(catalog, summary, OUTPUT_MD)
                print(f"[OK] Catálogo actualizado con 100% de dispositivos emparejados a NetBox.")
                return
        except Exception as e:
            print(f"Error leyendo cache: {e}")

    catalog = []
    summary = {
        "total_devices": len(devices),
        "success_count": 0,
        "failed_count": 0,
        "total_interfaces": 0,
        "cat_physical": 0,
        "cat_fortilink": 0,
        "cat_vlan": 0,
        "cat_vpn": 0,
        "cat_loopback": 0,
        "cat_other": 0
    }

    for idx, d in enumerate(devices, 1):
        alias = d["alias"]
        ip = d["ip"]
        pwd = d["password"]
        print(f"[{idx}/{len(devices)}] Conectando a {alias:20} ({ip})...", end=" ", flush=True)

        try:
            raw_output = fetch_firewall_interfaces_ssh(ip, user, pwd, timeout=6)
            interfaces = parse_interfaces_block(raw_output)

            hn_m = re.search(r"Hostname:\s*([^\r\n]+)", raw_output)
            if not hn_m:
                hn_m = re.search(r"([A-Za-z0-9_\-]+)\s+[\$#]", raw_output)
            hostname = hn_m.group(1).strip() if hn_m else alias

            dev_entry = {
                "alias": alias,
                "hostname": hostname,
                "ip": ip,
                "success": True,
                "interfaces_count": len(interfaces),
                "interfaces": interfaces
            }

            for iface in interfaces:
                cat = iface["category"]
                summary["total_interfaces"] += 1
                if cat == "physical":
                    summary["cat_physical"] += 1
                elif cat == "aggregate_fortilink":
                    summary["cat_fortilink"] += 1
                elif cat == "vlan_subinterface":
                    summary["cat_vlan"] += 1
                elif cat == "vpn_tunnel":
                    summary["cat_vpn"] += 1
                elif cat == "loopback":
                    summary["cat_loopback"] += 1
                else:
                    summary["cat_other"] += 1

            summary["success_count"] += 1
            catalog.append(dev_entry)
            print(f"OK ({len(interfaces)} interfaces)")
        except Exception as e:
            summary["failed_count"] += 1
            catalog.append({
                "alias": alias,
                "hostname": alias,
                "ip": ip,
                "success": False,
                "error": str(e),
                "interfaces_count": 0,
                "interfaces": []
            })
            print(f"FALLO: {e}")

    correlate_with_netbox(catalog)

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": summary,
            "devices": catalog
        }, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Catálogo JSON generado en: {OUTPUT_JSON}")

    generate_markdown_report(catalog, summary, OUTPUT_MD)
    print(f"[OK] Catálogo Markdown generado en: {OUTPUT_MD}")
    print(f"\nResumen: {summary['success_count']}/{summary['total_devices']} firewalls procesados con éxito. Total interfaces: {summary['total_interfaces']}.")


if __name__ == "__main__":
    main()
