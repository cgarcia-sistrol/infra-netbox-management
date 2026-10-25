#!/usr/bin/env python3
"""CLI para creación exclusiva de perfiles criptográficos B2B en NetBox.

Uso:
  uv run python scripts/netbox/ingest_b2b_crypto_profiles.py --dry-run
  uv run python scripts/netbox/ingest_b2b_crypto_profiles.py --commit
"""

import argparse
import sys
from netbox_ingest.runners.b2b_crypto_ingest import B2BCryptoIngestRunner


def main():
    parser = argparse.ArgumentParser(description="Ingesta de perfiles criptográficos B2B en NetBox")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Simulación sin escrituras")
    group.add_argument("--commit", action="store_true", help="Escritura en producción")

    args = parser.parse_args()

    runner = B2BCryptoIngestRunner(dry_run=args.dry_run)
    stats = runner.run()

    if stats["errors"]:
        print(f"\n[ALERTA] Finalizado con {len(stats['errors'])} errores.")
        sys.exit(1)
    else:
        print("\n[OK] Reconciliación de criptografía B2B finalizada con éxito.")
        sys.exit(0)


if __name__ == "__main__":
    main()
