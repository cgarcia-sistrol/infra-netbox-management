#!/usr/bin/env python3
"""CLI genérico de provisión idempotente de cables e infraestructura en NetBox.

Uso:
    uv run python scripts/provision_cables.py --file inputs/cables_esplandiu.json [--dry-run] [--verbose]
"""

import argparse
import os
import sys
from pathlib import Path

# Agregar src al sys.path para resolución de módulos locales
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from netbox_automation.dcim.cable_provisioner import CableProvisioner


def parse_args():
    parser = argparse.ArgumentParser(
        description="Aprovisionador genérico de cableado L1/L2 para sedes e infraestructura en NetBox."
    )
    parser.add_argument(
        "-f",
        "--file",
        required=True,
        type=str,
        help="Ruta al fichero declarativo JSON con la especificación de cables de la sede.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la ejecución validando interfaces sin crear cables en NetBox.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Muestra información extendida y de depuración.",
    )
    return parser.parse_args()


def print_summary(summary: dict, is_dry_run: bool):
    mode_str = "DRY-RUN (Simulación)" if is_dry_run else "REAL (Producción)"
    print(f"\n{'='*70}")
    print(f"       RESUMEN DE APROVISIONAMIENTO DE CABLES [{mode_str}]")
    print(f"{'='*70}")

    ensured = summary.get("interfaces_ensured", [])
    if ensured:
        print(f"\n[*] Interfaces Físicas Verificadas / Creadas ({len(ensured)}):")
        for item in ensured:
            act = item.get("action")
            dev = item.get("device")
            intf = item.get("interface")
            intf_id = item.get("id", "N/A")
            print(f"    - [{act:14}] {dev}:{intf} (ID: {intf_id})")

    created = summary.get("created", [])
    skipped = summary.get("skipped", [])
    conflicts = summary.get("conflicts", [])
    errors = summary.get("errors", [])

    print(f"\n[*] Cables Procesados:")
    print(f"    - Creados / Planificados : {len(created)}")
    print(f"    - Omitidos (Ya existentes): {len(skipped)}")
    print(f"    - Conflictos detectados  : {len(conflicts)}")
    print(f"    - Errores de ejecución   : {len(errors)}")

    if created:
        print(f"\n--- Detalle de Cables ({'Planificados' if is_dry_run else 'Creados'}): ---")
        for c in created:
            cid = f"[ID: {c.get('cable_id')}] " if "cable_id" in c else ""
            print(f"    + {cid}{c.get('endpoints')} | {c.get('type')} | {c.get('label')} - {c.get('description')}")

    if skipped:
        print("\n--- Detalle de Cables Omitidos (Idempotencia): ---")
        for s in skipped:
            print(f"    = [ID: {s.get('cable_id')}] {s.get('endpoints')} ({s.get('reason')})")

    if conflicts:
        print("\n[!] CONFLICTOS DETECTADOS:")
        for cf in conflicts:
            print(f"    ! {cf.get('endpoints')}: {cf.get('reason')}")

    if errors:
        print("\n[X] ERRORES ENCONTRADOS:")
        for err in errors:
            print(f"    X {err.get('endpoints')}: {err.get('error')}")

    print(f"\n{'='*70}\n")


def main():
    args = parse_args()
    input_path = Path(args.file)

    if not input_path.exists():
        print(f"Error: No existe el fichero especificado: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        provisioner = CableProvisioner()
        spec = provisioner.load_specification(input_path)
        print(f"[*] Especificación cargada: '{input_path.name}' para Sede: '{spec.get('site', 'Global')}'")
        print(f"[*] Total cables a verificar: {len(spec.get('cables', []))}")

        summary = provisioner.provision_cables(spec, dry_run=args.dry_run)
        print_summary(summary, is_dry_run=args.dry_run)

        if summary.get("errors") or summary.get("conflicts"):
            sys.exit(1)

    except Exception as e:
        print(f"\n[FATAL] Error procesando especificación: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
