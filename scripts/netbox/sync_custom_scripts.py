#!/usr/bin/env python3
"""Sincronizador idempotente de NetBox Custom Scripts vía REST API.

Permite publicar y actualizar scripts en NetBox de forma instantánea sin requerir
recompilación de imagen Docker ni reinicio de servicios ECS.

Uso:
    uv run python scripts/netbox/sync_custom_scripts.py
"""

import os
import sys
from pathlib import Path
import requests

# Agregar src al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from netbox_core.client import NetBoxClient

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "netbox_automation" / "custom_scripts"
MANAGED_SCRIPTS = [
    "dcim_01_device_wizard.py",
    "dcim_02_device_lifecycle.py",
    "ipam_01_quick_allocate.py",
]


def sync_scripts():
    client = NetBoxClient()
    upload_url = f"{client.base_url}/api/extras/scripts/upload/"
    headers = {"Authorization": f"Token {client.token}"}

    print(f"[*] Conectando a NetBox ({client.base_url})...")

    # Obtener lista actual de scripts
    try:
        current = client._request("GET", "extras/scripts")
        existing_names = {r.get("display", "") for r in current.get("results", [])}
        print(f"[*] Scripts actualmente registrados: {len(current.get('results', []))}")
    except Exception as e:
        print(f"[!] Error al consultar scripts existentes: {e}")
        existing_names = set()

    for script_name in MANAGED_SCRIPTS:
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            print(f"[!] Archivo no encontrado: {script_path}")
            continue

        with open(script_path, "rb") as f:
            files = {"file": (script_name, f, "text/x-python")}
            # Intentar primero PUT para actualización en caliente
            detail_url = f"{upload_url}{script_name}/"
            resp = requests.put(detail_url, headers=headers, files=files)

            if resp.status_code in (200, 204):
                print(f"[+] [ACTUALIZADO] {script_name} actualizado con éxito en NetBox.")
            elif resp.status_code == 404:
                # Si no existe, crear con POST
                f.seek(0)
                files = {"file": (script_name, f, "text/x-python")}
                post_resp = requests.post(upload_url, headers=headers, files=files)
                if post_resp.status_code == 201:
                    print(f"[+] [CREADO] {script_name} publicado con éxito en NetBox.")
                else:
                    print(f"[-] [ERROR] Fallo al crear {script_name}: {post_resp.status_code} - {post_resp.text}")
            else:
                print(f"[-] [ERROR] Fallo al actualizar {script_name}: {resp.status_code} - {resp.text}")

    # Verificación final
    final = client._request("GET", "extras/scripts")
    print(f"\n{'='*60}")
    print(f"[*] Verificación final: {final.get('count', 0)} scripts disponibles en NetBox:")
    for item in final.get("results", []):
        name = item.get("name")
        display_url = item.get("display_url")
        executable = item.get("is_executable")
        print(f"    - [{name}] -> {display_url} (Ejecutable: {executable})")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    sync_scripts()
