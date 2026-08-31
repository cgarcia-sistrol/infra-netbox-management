---
name: project-conventions
description: >
  Convenciones de ubicación de archivos y taxonomía del proyecto infra-netbox-management.
  Activar al generar, organizar o guardar entregables, scripts, código, documentación o recursos.
---

# Convenciones del Proyecto (infra-netbox-management)

Esta skill define la taxonomía de carpetas y las reglas de enrutamiento obligatorio de archivos para el workspace del proyecto.

---

## 🎯 Cuándo Activar esta Skill (Disparadores / Triggers)

Esta skill debe activarse de forma autónoma o explícita cuando:
1. **Generación de Entregables**: Se vaya a crear o guardar documentación técnica, playbooks o informes técnicos.
2. **Creación de Diagramas o Recursos**: Se generen esquemas Mermaid (`.mmd`), imágenes (`.png`, `.jpg`) o recursos gráficos de apoyo en `docs/resources/`.
3. **Escritura de Scripts**: Se creen o modifiquen scripts de automatización, ingestión o sincronización NetBox en `scripts/`.
4. **Procesamiento de Insumos / Entradas**: Se lean o procesen documentos, archivos CSV, YAML, exportaciones de inventario u otros recursos depositados en `inputs/`.
5. **Organización del Workspace**: Se requiera mover, clasificar o auditar la ubicación de archivos en el proyecto.

### 🛑 Cuándo NO Activar (Delegación a otras Skills):
- **Generación y exportación de documentos Markdown/PDF/HTML**: Delegar en la skill global `document-creator`.
- **Estándares de calidad de código**: Delegar en la skill global `code-conventions`.
- **Arquitectura de paquetes Python y entorno `uv`**: Delegar en la skill global `project-code-structure`.

---

## 📄 Parámetros Documentales (Metadatos para `document-creator`)

| Parámetro | Valor | Descripción |
| :--- | :--- | :--- |
| `DOC_PREFIX` | `INFRA.NETBOX` | Prefijo para nombres de archivo y códigos de documento |
| `DOC_TARGET_DIR` | `docs/` | Carpeta de salida para documentos técnicos e informes |
| `PLAYBOOK_TARGET_DIR` | `docs/playbooks/` | Carpeta de salida para playbooks y procedimientos |
| `INPUTS_DIR` | `inputs/` | Carpeta para documentos, inventarios y recursos de entrada |

---

## 📁 Taxonomía y Estructura de Directorios

### 1. Código Fuente (`src/`)
- Código fuente principal en Python (`src-layout`).
- Modelos, clientes de API NetBox y utilidades de la aplicación.
- Ejecución aislada en `.venv` mediante `uv run`.

### 2. Documentación y Entregables (`docs/`)
- Documentos de arquitectura, HLD/LLD, actas e informes técnicos.
- **Recursos (`docs/resources/`)**: Diagramas e imágenes de apoyo.
- **Playbooks (`docs/playbooks/`)**: Procedimientos y guías paso a paso.

### 3. Scripts de Soporte y Automatización (`scripts/`)
- `scripts/netbox/`: Scripts de interacción y sincronización con la API de NetBox.
- `scripts/import/`: Scripts de carga masiva, parsing y transformación de datos.
- `scripts/other/`: Utilidades generales no categorizadas.

### 4. Pruebas Automatizadas (`tests/`)
- Pruebas unitarias y de integración de scripts y módulos.

### 5. Documentos y Recursos de Entrada (`inputs/`)
- Documentos, inventarios (CSV/Excel/JSON), configuraciones o recursos depositados como insumo para el proyecto.

---

## 🧹 Reglas de Limpieza y Gobernanza
- **Cero basuras en la raíz**: Prohibido crear archivos o scripts sueltos en el directorio raíz.
- **Enrutamiento Autónomo**: Todo archivo generado o procesado debe enrutarse automáticamente a su directorio correspondiente.
