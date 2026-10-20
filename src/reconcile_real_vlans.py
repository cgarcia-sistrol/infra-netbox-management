#!/usr/bin/env python3
"""Generador del payload de reconciliación integral de VLANs y Prefijos en NetBox."""

import json
from pathlib import Path
from typing import Any, Dict, List

from netbox_ingest.firewall_vlans_parser import parse_firewall_vlans
from netbox_ingest.ipam_definitions import STANDARD_VLANS, SPOKE_SITES

# Mapeos exactos de NetBox
SITE_SLUG_TO_ID = {
    "arcelormittal-aviles": 5,
    "arcelormittal-verina": 6,
    "coren-cat": 11,
    "coren-rolls": 12,
    "damm": 14,
    "delegacion-alcala-de-henares": 15,
    "delegacion-barcelona-zona-franca": 17,
    "delegacion-ibiza": 19,
    "delegacion-molins-de-rei": 21,
    "delegacion-palma-de-mallorca": 22,
    "delegacion-sant-boi-de-llobregat": 23,
    "delegacion-sant-cugat-del-valles": 24,
    "delegacion-sevilla": 25,
    "eamsa": 26,
    "el-pozo": 27,
    "fompedraza": 29,
    "guijuelo-fonz": 33,
    "guijuelo-milagros": 34,
    "guijuelo-monzon": 35,
    "guijuelo-san-millan": 36,
    "ilas-reny-picot": 46,
    "inleit": 47,
    "iveco-madrid": 50,
    "iveco-valladolid": 51,
    "leche-celta-avila": 53,
    "leche-celta-meruelo": 54,
    "leche-celta-pontedeume": 55,
    "oficina-gijon": 63,
    "packbenefit": 64,
    "madrid-cpd": 82,
    "jesp": 83,
    "test-jesp": 84,
}

SITE_ID_TO_VG_ID = {
    5: 16,
    6: 17,
    11: 18,
    12: 19,
    14: 20,
    15: 7,
    17: 3,
    19: 10,
    21: 11,
    22: 4,
    23: 12,
    24: 13,
    25: 5,
    26: 21,
    27: 9,
    29: 22,
    33: 25,
    34: 28,
    35: 26,
    36: 27,
    46: 8,
    47: 24,
    50: 15,
    51: 23,
    53: 31,
    54: 30,
    55: 29,
    63: 14,
    64: 6,
    82: 1,
    83: 2,
    84: 32,
}

ROLE_SLUG_TO_ID = {
    "supernet-container": 1,
    "lan-datos-cable": 2,
    "lan-wifi-corp": 3,
    "lan-voz-ip": 4,
    "lan-impresoras": 5,
    "lan-servidores": 6,
    "lan-ot-industrial": 7,
    "lan-invitados": 8,
    "lan-cctv-seguridad": 9,
    "cloud-transit-sdwan": 10,
    "cloud-workload": 11,
    "vpn-dialup-pool": 12,
    "b2b-extranet-nat": 13,
    "bgp-peering-apipa": 14,
    "inter-hub-transit": 15,
    "fotovoltaica-solar": 16,
    "legacy-flat-network": 17,
    "lan-gestion-infra": 18,
    "lan-restringida-rstd": 19,
}

ALIAS_TO_SITE_SLUG = {
    "HUB-00": "madrid-cpd",
    "HUB-02": "jesp",
    "ZNF": "delegacion-barcelona-zona-franca",
    "PDM": "delegacion-palma-de-mallorca",
    "SEV": "delegacion-sevilla",
    "PBF": "packbenefit",
    "ADH": "delegacion-alcala-de-henares",
    "ILAS": "ilas-reny-picot",
    "EPZ": "el-pozo",
    "IBZ": "delegacion-ibiza",
    "MDR": "delegacion-molins-de-rei",
    "SBL": "delegacion-sant-boi-de-llobregat",
    "SCV": "delegacion-sant-cugat-del-valles",
    "GIJ-OFI": "oficina-gijon",
    "IVECO-MAD": "iveco-madrid",
    "ARC-AVI": "arcelormittal-aviles",
    "ARC-GIJ": "arcelormittal-verina",
    "COR-SCI": "coren-cat",
    "COR-ARR": "coren-rolls",
    "DAMM": "damm",
    "EAMSA": "eamsa",
    "FOM": "fompedraza",
    "IVECO-VALL": "iveco-valladolid",
    "INLEIT": "inleit",
    "FONZ": "guijuelo-fonz",
    "MONZON": "guijuelo-monzon",
    "SANMILLAN": "guijuelo-san-millan",
    "MILAGROS": "guijuelo-milagros",
    "TEST-JESP": "test-jesp",
    "LCP": "leche-celta-pontedeume",
    "LCM": "leche-celta-meruelo",
    "LCA": "leche-celta-avila",
}


def get_role_id_and_vlan_name(vid: int, alias: str, site_slug: str) -> tuple[int, str]:
    upper_slug = site_slug.upper()
    alias_clean = alias.strip().upper()
    
    if vid == 10:
        return ROLE_SLUG_TO_ID["lan-datos-cable"], f"LAN_Datos_Cable_{upper_slug}"
    elif vid == 11:
        return ROLE_SLUG_TO_ID["lan-wifi-corp"], f"LAN_WiFi_Corp_{upper_slug}"
    elif vid == 20:
        return ROLE_SLUG_TO_ID["lan-invitados"], f"LAN_Invitados_{upper_slug}"
    elif vid == 30:
        return ROLE_SLUG_TO_ID["lan-impresoras"], f"LAN_Impresoras_{upper_slug}"
    elif vid == 40:
        return ROLE_SLUG_TO_ID["lan-cctv-seguridad"], f"LAN_CCTV_Seguridad_{upper_slug}"
    elif vid == 41:
        return ROLE_SLUG_TO_ID["lan-cctv-seguridad"], f"LAN_Temp_CCTV_{upper_slug}"
    elif vid == 50:
        return ROLE_SLUG_TO_ID["lan-restringida-rstd"], f"LAN_Restringida_RSTD_{upper_slug}"
    elif vid == 80:
        return ROLE_SLUG_TO_ID["lan-gestion-infra"], f"LAN_Gestion_Infra_{upper_slug}"
    elif vid == 90:
        return ROLE_SLUG_TO_ID["lan-servidores"], f"LAN_Servidores_{upper_slug}"
    elif vid == 91:
        return ROLE_SLUG_TO_ID["lan-servidores"], f"LAN_Servidores_Temp_{upper_slug}"
    elif vid == 92:
        return ROLE_SLUG_TO_ID["lan-servidores"], f"LAN_Servidores_R2_{upper_slug}"
    elif vid in (60, 61, 62, 63, 64, 65, 66, 67, 69):
        role_id = ROLE_SLUG_TO_ID["lan-ot-industrial"]
        if vid == 60:
            return role_id, f"LAN_OT_Industrial_{upper_slug}"
        elif vid == 61:
            suffix = f"_{alias_clean}" if alias_clean and alias_clean != "IOT" else "_61"
            return role_id, f"LAN_OT{suffix}_{upper_slug}"
        else:
            return role_id, f"LAN_OT_{vid}_{upper_slug}"
    else:
        return ROLE_SLUG_TO_ID["lan-datos-cable"], f"VLAN_{vid}_{upper_slug}"


def build_payload() -> Dict[str, Any]:
    md_file = Path("/home/carlos/projects-ag/infra-netbox-management/inputs/vlans_firewalls_consolidadas.md")
    devices = parse_firewall_vlans(md_file)
    print(f"✅ Parseados {len(devices)} firewalls de producción")

    desired_vlans = []
    desired_prefixes = []

    # 1. Sedes auditadas desde Firewalls
    for dev in devices:
        alias = dev["alias"]
        site_slug = ALIAS_TO_SITE_SLUG.get(alias)
        if not site_slug or site_slug not in SITE_SLUG_TO_ID:
            print(f"⚠️ Advertencia: No se encontró Site para alias '{alias}'")
            continue
        
        site_id = SITE_SLUG_TO_ID[site_slug]
        vlan_group_id = SITE_ID_TO_VG_ID[site_id]
        
        for v in dev["vlans"]:
            vid = v["vid"]
            cidr = v["cidr"]
            gw = v["gateway_ip"]
            role_id, vlan_name = get_role_id_and_vlan_name(vid, v["alias"], site_slug)
            
            desired_vlans.append({
                "vid": vid,
                "name": vlan_name,
                "site": site_id,
                "group": vlan_group_id,
                "role": role_id,
                "status": "active",
                "description": f"GW: {gw} | Máscara: {v['mask']} | Alias: {v['alias']}",
                "site_slug": site_slug,
            })
            
            desired_prefixes.append({
                "prefix": cidr,
                "site": site_id,
                "role": role_id,
                "status": "active",
                "description": f"Subred {vlan_name} (GW: {gw})",
                "vid": vid,
                "site_slug": site_slug,
            })

    # 2. Sedes Spoke sin FW en inventario (Leche Celta Pontedeume, Meruelo, Ávila)
    leche_celta = [
        {"slug": "leche-celta-pontedeume", "octet": 181, "name": "Leche Celta Pontedeume"},
        {"slug": "leche-celta-meruelo", "octet": 182, "name": "Leche Celta Meruelo"},
        {"slug": "leche-celta-avila", "octet": 183, "name": "Leche Celta Ávila"},
    ]
    for lc in leche_celta:
        site_slug = lc["slug"]
        octet = lc["octet"]
        site_id = SITE_SLUG_TO_ID[site_slug]
        vlan_group_id = SITE_ID_TO_VG_ID[site_id]
        
        for sv in STANDARD_VLANS:
            vid = sv["vid"]
            third = sv["third_octet"]
            mask = sv.get("mask", "/24")
            gw_off = sv.get("gateway_offset", 254)
            gw_ip = f"10.{octet}.{third}.{gw_off}"
            cidr = f"10.{octet}.{third}.0{mask}"
            role_id = ROLE_SLUG_TO_ID[sv["role_slug"]]
            vlan_name = f"{sv['name']}_{site_slug.upper()}"
            
            desired_vlans.append({
                "vid": vid,
                "name": vlan_name,
                "site": site_id,
                "group": vlan_group_id,
                "role": role_id,
                "status": "active",
                "description": f"GW: {gw_ip} | {sv['description']}",
                "site_slug": site_slug,
            })
            
            desired_prefixes.append({
                "prefix": cidr,
                "site": site_id,
                "role": role_id,
                "status": "active",
                "description": f"Subred {vlan_name} (GW: {gw_ip})",
                "vid": vid,
                "site_slug": site_slug,
            })

    # 3. Contenedores /16 de cada una de las 32 sedes (Hubs + Spokes)
    site_containers = []
    
    # Hub 00 (10.148.0.0/16)
    site_containers.append({
        "prefix": "10.148.0.0/16",
        "site": 82,
        "role": 1,
        "status": "container",
        "description": "Contenedor Hub: Madrid CPD (10.148.0.0/16)",
    })
    # Hub 02 (10.152.0.0/16)
    site_containers.append({
        "prefix": "10.152.0.0/16",
        "site": 83,
        "role": 1,
        "status": "container",
        "description": "Contenedor Hub: JESP (10.152.0.0/16)",
    })
    
    for spoke in SPOKE_SITES:
        slug = spoke["site_slug"]
        octet = spoke["second_octet"]
        site_id = SITE_SLUG_TO_ID[slug]
        site_containers.append({
            "prefix": f"10.{octet}.0.0/16",
            "site": site_id,
            "role": 1,
            "status": "container",
            "description": f"Contenedor Sede: {spoke['site_name']} (10.{octet}.0.0/16)",
        })

    payload = {
        "vlans": desired_vlans,
        "subnets": desired_prefixes,
        "site_containers": site_containers,
    }
    
    out_file = Path("/home/carlos/projects-ag/infra-netbox-management/inputs/reconciliation_payload.json")
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"🎯 Total VLANs a aprovisionar/reconciliar: {len(desired_vlans)}")
    print(f"🎯 Total Subredes a aprovisionar/reconciliar: {len(desired_prefixes)}")
    print(f"🎯 Total Contenedores /16: {len(site_containers)}")
    print(f"💾 Guardado payload en {out_file}")
    return payload


if __name__ == "__main__":
    build_payload()
