#!/usr/bin/env python3
"""CLI para modelado e ingesta automatizada de túneles VPN B2B en NetBox."""

import argparse
import logging
import sys
from netbox_ingest.runners.vpn_b2b_batch_runner import B2BVPNBatchRunner, CATALOG_VPN_PATH


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingesta y conciliación automatizada de túneles VPN B2B en NetBox"
    )
    parser.add_argument(
        "--catalog",
        default=CATALOG_VPN_PATH,
        help=f"Ruta al catálogo JSON de túneles (por defecto: {CATALOG_VPN_PATH})",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Aplica los cambios en NetBox (por defecto ejecuta en modo dry-run)",
    )
    parser.add_argument(
        "--hub",
        choices=["HUB-00", "HUB-02"],
        default=None,
        help="Filtra la ejecución para un único Hub (HUB-00 o HUB-02)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Activa logs detallados de depuración",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    dry_run = not args.commit
    print("=" * 60)
    print(f" Ingesta Automatizada de Túneles VPN B2B en NetBox")
    print(f" Modo: {'DRY-RUN (Simulación Segura)' if dry_run else 'COMMIT (Cambios Reales)'}")
    print(f" Catálogo: {args.catalog}")
    if args.hub:
        print(f" Filtro Hub: {args.hub}")
    print("=" * 60)

    runner = B2BVPNBatchRunner(catalog_path=args.catalog, dry_run=dry_run)
    summary = runner.run(hub_filter=args.hub)

    print("\n" + "=" * 60)
    print(" Resumen de Ejecución:")
    print(f" - Tunnel Group ID: {summary['tunnel_group']}")
    print(f" - Tenants Creados: {summary['tenants_created']}")
    print(f" - Interfaces Virtuales Creadas: {summary['interfaces_created']}")
    print(f" - Túneles Creados: {summary['tunnels_created']}")
    print(f" - Túneles Actualizados: {summary['tunnels_updated']}")
    print(f" - Terminaciones Creadas: {summary['terminations_created']}")

    if summary["errors"]:
        print(f"\n [ERROR] Se registraron {len(summary['errors'])} fallos:")
        for err in summary["errors"]:
            print(f"   * {err['hub']} - {err['tunnel']}: {err['error']}")
        return 1

    print("\n Ingesta completada con éxito.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
