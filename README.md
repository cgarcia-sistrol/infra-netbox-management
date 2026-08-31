# infra-netbox-management

Gestión automatizada e ingesta de la estructura organizativa y componentes de infraestructura en NetBox.

## Requisitos y Ejecución

Gestionado mediante `uv`:

```bash
# Ejecutar tests
uv run pytest

# Ingesta en modo dry-run
uv run python src/ingest_organization.py --dry-run
```
