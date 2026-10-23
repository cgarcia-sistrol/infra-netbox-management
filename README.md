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

## Documentación y Hoja de Ruta

- [Procedimiento Maestro de Ingesta y Gestión de NetBox](docs/INFRA.NETBOX.Procedimiento_Ingesta_Gestion_NetBox.md)
- [Backlog Técnico y Hoja de Ruta Futura](docs/INFRA.NETBOX.Roadmap_y_Backlog_Futuro.md)

## Dependencias y Enlaces Simbólicos Recomendados

Este proyecto se apoya en insumos y documentación técnica gestionados en el repositorio hermano `infra-redes`. Para facilitar el acceso cruzado localmente, se recomienda crear los siguientes enlaces simbólicos dentro de `docs/`:

```bash
ln -s ../../infra-redes/inputs/direccionamiento/ docs/direccionamiento
ln -s ../../infra-redes/docs/ docs/infra-redes-docs
```

> **Nota:** Estos enlaces están excluidos en `.gitignore` para no acoplar rutas absolutas o relativas locales al repositorio.

