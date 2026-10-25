#!/usr/bin/env python3
"""CLI para ingesta y conciliación de túneles VPN de infraestructura (no-B2B) en NetBox.

Uso:
  uv run python scripts/netbox/ingest_firewall_infra_vpn.py --dry-run
  uv run python scripts/netbox/ingest_firewall_infra_vpn.py --commit
"""

import argparse
import sys
from netbox_ingest.runners.vpn_infra_ingest import VPNInfraIngestRunner


def main():
    parser = argparse.ArgumentParser(description="Ingesta de túneles VPN de infraestructura en NetBox")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Modo simulación sin escrituras en NetBox")
    group.add_argument("--commit", action="store_true", help="Modo producción con escritura en NetBox")

    args = parser.parse_args()

    runner = VPNInfraIngestRunner(dry_run=args.dry_run)
    stats = runner.run()

    if stats["errors"]:
        print(f"\n[ALERTA] Finalizado con {len(stats['errors'])} errores.")
        sys.exit(1)
    else:
        print("\n[OK] Ingesta finalizada con éxito.")
        sys.exit(0)


if __name__ == "__main__":
    main()
