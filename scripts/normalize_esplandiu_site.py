#!/usr/bin/env python3
"""Script de normalización integral de la sede Oficina Madrid - Esplandiú en NetBox.

1. Reasigna y renombra el VLANGroup (ID 2) y las 11 VLANs a Oficina Madrid - Esplandiú.
2. Asocia los prefijos IPAM del bloque 10.152.0.0/16 y sus subredes a la sede.
3. Vincula en modo tagged las 11 subinterfaces del Firewall FGT100-JES con sus VLANs de NetBox.
4. Reasigna los 11 Puntos de Acceso Wi-Fi a Oficina Madrid - Esplandiú.
5. Verifica cero dependencias en JESP y elimina el Site residual JESP.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from netbox_ingest.client import NetBoxClient


def normalize_esplandiu(dry_run: bool = False):
    client = NetBoxClient()
    print(f"=== Normalización de Sede Esplandiú [Modo: {'DRY-RUN' if dry_run else 'REAL'}] ===")

    # 1. Obtener Sedes
    target_site_res = client.get("dcim/sites", params={"name": "Oficina Madrid - Esplandiú"})
    if not target_site_res.get("results"):
        raise RuntimeError("No se encontró la sede destino 'Oficina Madrid - Esplandiú'")
    target_site = target_site_res["results"][0]
    target_site_id = target_site["id"]
    print(f"[*] Sede destino: {target_site['name']} (ID: {target_site_id})")

    jesp_site_res = client.get("dcim/sites", params={"name": "JESP"})
    jesp_site_id = jesp_site_res["results"][0]["id"] if jesp_site_res.get("results") else None
    if jesp_site_id:
        print(f"[*] Sede residual a depurar: JESP (ID: {jesp_site_id})")
    else:
        print("[!] Sede JESP ya no existe o ya fue eliminada.")

    # 2. Actualizar VLAN Group si existe
    print("\n--- Paso 1: Migración y Renombrado de VLAN Group y VLANs ---")
    vg_res = client.get("ipam/vlan-groups", params={"id": 2})
    if vg_res.get("results"):
        vg = vg_res["results"][0]
        if vg.get("scope_id") != target_site_id:
            print(f"  - Actualizando VLAN Group {vg['name']} (ID: {vg['id']}) a Site {target_site_id}...")
            if not dry_run:
                client.patch("ipam/vlan-groups", vg["id"], {
                    "name": "VLAN-GROUP-OFICINA-MADRID-ESPLANDIU",
                    "slug": "vlan-group-oficina-madrid-esplandiu",
                    "scope_type": "dcim.site",
                    "scope_id": target_site_id,
                    "description": "Dominio L2 local para Oficina Madrid - Esplandiú",
                })
        else:
            print(f"  - VLAN Group {vg['name']} ya tiene scope en Site {target_site_id}")

    # Obtener todas las VLANs del grupo 2 o de JESP o de Esplandiú
    vlan_map = {} # vid -> vlan_id
    vlans_in_group = client.get_all("ipam/vlans", params={"group_id": 2})
    for vlan in vlans_in_group:
        vid = vlan["vid"]
        old_name = vlan["name"]
        new_name = old_name.replace("_JESP", "_OFICINA-MADRID-ESPLANDIU")
        curr_site_id = vlan.get("site", {}).get("id") if vlan.get("site") else None
        
        if curr_site_id != target_site_id or old_name != new_name:
            print(f"  - VLAN VID {vid} (ID: {vlan['id']}): '{old_name}' -> '{new_name}' (Site {target_site_id})")
            if not dry_run:
                client.patch("ipam/vlans", vlan["id"], {
                    "site": target_site_id,
                    "name": new_name,
                })
        else:
            print(f"  - VLAN VID {vid} (ID: {vlan['id']}): ya normalizada.")
        vlan_map[vid] = vlan["id"]

    # 3. Asignar Site a Prefijos IPAM
    print("\n--- Paso 2: Asociación de Prefijos IPAM a la Sede ---")
    target_prefixes = [
        "10.152.0.0/16",
        "10.152.10.0/24",
        "10.152.11.0/24",
        "10.152.12.0/24",
        "10.152.13.0/24",
        "10.152.14.0/24",
        "10.152.15.0/24",
        "10.152.16.0/24",
        "10.152.17.0/25",
        "10.152.18.0/24",
        "192.168.48.0/24",
        "192.168.100.0/24",
    ]

    for pref_str in target_prefixes:
        res = client.get("ipam/prefixes", params={"prefix": pref_str})
        for p in res.get("results", []):
            curr_scope = p.get("scope")
            curr_scope_id = curr_scope.get("id") if curr_scope else None
            if curr_scope_id != target_site_id:
                print(f"  - Prefijo {pref_str} (ID: {p['id']}): scope '{curr_scope_id}' -> '{target_site_id}'")
                if not dry_run:
                    client.patch("ipam/prefixes", p["id"], {
                        "scope_type": "dcim.site",
                        "scope_id": target_site_id,
                    })
            else:
                print(f"  - Prefijo {pref_str} (ID: {p['id']}): ya tiene scope {target_site_id}")

    # 4. Vincular subinterfaces de FGT100-JES
    print("\n--- Paso 3: Vinculación L2 en Firewall FGT100-JES ---")
    fw_dev_res = client.get("dcim/devices", params={"name": "FGT100-JES"})
    if not fw_dev_res.get("results"):
        print("[!] No se encontró el dispositivo FGT100-JES")
    else:
        fw_id = fw_dev_res["results"][0]["id"]
        fw_ifaces = client.get_all("dcim/interfaces", params={"device_id": fw_id})
        
        name_to_vid = {
            "VLAN-10": 10,
            "VLAN-11": 11,
            "VLAN-20": 20,
            "VLAN-30": 30,
            "VLAN-40": 40,
            "VLAN-50": 50,
            "VLAN-60": 60,
            "VLAN-80": 80,
            "VLAN-90": 90,
            "VLAN-91": 91,
            "VLAN-92": 92,
        }

        for iface in fw_ifaces:
            if_name = iface["name"]
            if if_name in name_to_vid:
                target_vid = name_to_vid[if_name]
                target_vlan_id = vlan_map.get(target_vid)
                if not target_vlan_id:
                    print(f"  [!] No se encontró ID de VLAN para VID {target_vid}")
                    continue

                curr_tagged = [v["id"] for v in iface.get("tagged_vlans", [])]
                if target_vlan_id not in curr_tagged:
                    print(f"  - Interfaz {if_name} (ID: {iface['id']}): asignando tagged_vlan VID {target_vid} (ID: {target_vlan_id})")
                    if not dry_run:
                        client.patch("dcim/interfaces", iface["id"], {
                            "mode": "tagged",
                            "tagged_vlans": [target_vlan_id],
                        })
                else:
                    print(f"  - Interfaz {if_name}: ya tiene tagged_vlan {target_vid}")

    # 5. Reasignar Puntos de Acceso Wi-Fi
    print("\n--- Paso 4: Reasignación de Puntos de Acceso Wi-Fi ---")
    if jesp_site_id:
        ap_devs = client.get_all("dcim/devices", params={"site_id": jesp_site_id})
        for ap in ap_devs:
            print(f"  - AP {ap['name']} (ID: {ap['id']}): reasignando de Site {jesp_site_id} a {target_site_id}")
            if not dry_run:
                client.patch("dcim/devices", ap["id"], {"site": target_site_id})
    else:
        print("  - No hay APs en JESP para reasignar.")

    # 6. Eliminar Site JESP
    print("\n--- Paso 5: Depuración y Eliminación de Site JESP ---")
    if jesp_site_id:
        dev_cnt = client.get("dcim/devices", params={"site_id": jesp_site_id}).get("count", 0)
        vlan_cnt = client.get("ipam/vlans", params={"site_id": jesp_site_id}).get("count", 0)
        pref_cnt = client.get("ipam/prefixes", params={"site_id": jesp_site_id}).get("count", 0)

        print(f"  - Auditoría de dependencias en JESP: Devices={dev_cnt}, VLANs={vlan_cnt}, Prefixes={pref_cnt}")
        if dev_cnt == 0 and vlan_cnt == 0 and pref_cnt == 0:
            print(f"  [*] Cero dependencias confirmadas. Procediendo a eliminar Site JESP (ID: {jesp_site_id})...")
            if not dry_run:
                client.delete("dcim/sites", jesp_site_id)
                print("  [+] Site JESP eliminado con éxito.")
            else:
                print("  [+] DRY-RUN: Se eliminaría el Site JESP.")
        else:
            print(f"  [!] ALERTA: No se puede eliminar JESP porque aún tiene dependencias activas.")
    else:
        print("  - Site JESP no presente.")

    print("\n=== Proceso de Normalización Finalizado con Éxito ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalizar la sede Oficina Madrid - Esplandiú en NetBox")
    parser.add_argument("--dry-run", action="store_true", help="Ejecutar en modo simulación")
    args = parser.parse_args()

    normalize_esplandiu(dry_run=args.dry_run)
