# Backlog Técnico y Hoja de Ruta Futura de NetBox

> **Documento de Registro y Planificación**: Hoja de ruta para las siguientes fases de ingesta, manuales de procedimiento operativo y arquitectura de automatizaciones e integraciones en el proyecto `infra-netbox-management`.

---

## 1. Fase 4 (Completitud): Puntos de Acceso (APs), Routers y Gestión de SIMs 4G

### 1.1 Ingesta de Puntos de Acceso Wi-Fi (Wireless Access Points)
- **Alcance**: Incorporar el parque de APs corporativos (ej. Ubiquiti UniFi, FortiAP) vinculándolos a su `Site`, `Location` y switch/puerto PoE correspondiente.
- **Configuración de Interfaces**: Mapear interfaces físicas Gigabit PoE y subinterfaces inalámbricas asociadas a las VLANs correspondientes (`VLAN-11` Wi-Fi Corp, `VLAN-20` Invitados).
- **Asignación IP**: Registrar IP de gestión (`VLAN-80` / `10.X.17.X`).

### 1.2 Ingesta de Routers Celulares / Perimetrales (ej. Milesight 4G/5G, Teltonika)
- **Alcance**: Dispositivos perimetrales y de contingencia para sedes remotas y cuadros de control.
- **Mapeo de Interfaces**: Puertos LAN Ethernet, interfaz celular `wwan0`/`cellular0`, y túneles VPN asociados.

### 1.3 Análisis Técnico: ¿Es NetBox adecuado para la gestión de tarjetas SIM de routers 4G?
- **Dictamen**: **Sí, es perfectamente viable y común en NetBox**, existiendo dos formas de abordarlo:
  1. **Enfoque Nativo Estándar (Recomendado sin plugins externos)**:
     - **Custom Fields en `Device` o en interfaz `Cellular`**:
       - `sim_iccid` (Texto, número único de tarjeta SIM de 19-20 dígitos).
       - `sim_msisdn` (Texto, número de teléfono asignado).
       - `sim_operator` (Selección: Telefónica, Vodafone, Orange, etc.).
       - `sim_pin` / `sim_puk` (si aplica o referenciado a bóveda).
       - `sim_apn` (Texto: APN contratado, ej. IP fija privada o pública).
     - **Ventajas**: Cero dependencia de plugins de terceros; compatible con actualizaciones mayores de NetBox; fácilmente consultable por API y scripts.
  2. **Enfoque Avanzado (Plugin NetBox)**:
     - Uso de plugins de la comunidad como `netbox-sim-plugin` o modelado mediante objetos de inventario (`Inventory Items` vinculados al Device).
     - Añade entidad separada para el ciclo de vida de la SIM (stock, asignada, dada de baja).
  - **Conclusión**: Se recomienda implementar el **Enfoque Nativo con Custom Fields** en interfaces celulares / routers, evitando complejidad adicional y manteniendo la fuente de verdad centralizada.

---

## 2. Planificación de Fases Siguientes (Fases 5 a 7)

Conforme a la metodología definida en `INFRA.NETBOX.Procedimiento_Ingesta_Gestion_NetBox.md`:

### 2.1 Fase 5: Conectividad Física, Enlaces WAN y Cableado DCIM
- **Circuitos y Proveedores (`Circuits`, `Providers`, `Circuit Types`)**:
  - Registro de accesos a Internet FTTH, enlaces dedicados MPLS/Macrolan y conectividad 4G.
  - Vinculación de circuitos con los puertos físicos `wan1` y `wan2` de los firewalls y routers mediante `Circuit Terminations`.
- **Cableado Físico (`Cables`)**:
  - Trazado de cables de parcheo UTP y fibra (ej. interconexiones Firewall `a`/`b` hacia Switch puertos LAG FortiLink; enlaces de uplink entre switches; parcheo de servidores en CPD).

### 2.2 Fase 6: Virtualización e Infraestructura Cloud Multi-Tenant
- **Plataformas de Virtualización On-Premise**:
  - Clústeres Proxmox (`hub0`, `hub2dell`, `hub2hpe`) y vCenter si aplica.
  - Ingesta de Clústeres, Nodos (Hosts), Máquinas Virtuales (VMs) y Contenedores (LXCs), vinculando vNICs a las VLANs correspondientes de NetBox.
- **Entornos Cloud (AWS y Azure)**:
  - Modelado de VPCs/VNets, subredes públicas/privadas, Transit Gateways y Virtual Network Gateways.
  - Registro de VMs e instancias EC2 clave como Virtual Machines en NetBox.

### 2.3 Fase 7: Servicios de Red, Config Contexts y Source of Truth (SoT)
- **Servicios de Red (`Services`)**:
  - Mapeo de puertos y protocolos en escucha (`HTTPS/443`, `SSH/22`, `BGP/179`, `DNS/53`, `LDAPS/636`).
- **Contextos de Configuración (`Config Contexts`)**:
  - Variables contextuales JSON/YAML por Sede, Rol o Plataforma (Syslog, NTP, DNS corporativo, ASNs BGP, rangos DHCP).
  - Habilitación de NetBox como motor de generación de configuración (Ansible / Terraform / Scripts FortiOS).

---

## 3. Manual de Operación y Procedimientos de Gestión de Dispositivos

Se desarrollará un manual operativo orientado tanto a consultores/auditores externos como a técnicos de operaciones internas:

### 3.1 Consulta Sencilla de Redes e Infraestructura para Auditores
- **Navegación Visual en GUI**:
  - Mapa de Sedes (`Organization > Sites`): Selección de sede y vista de prefijos, VLANs y dispositivos asociados.
  - Árbol IPAM (`IPAM > Prefixes`): Vista jerárquica de bloques corporativos (`/16`), subredes de sede (`/24`) y tasa de utilización.
  - Inventario de VLANs (`IPAM > VLANs`): Filtrado por Sede para consultar la matriz estándar (`VLAN-10` a `VLAN-90`).
  - Tabla de Dispositivos (`DCIM > Devices`): Filtrado por Rol (`firewall`, `switch`, `server`) con visualización inmediata de `Primary IP`, estado y modelo.
- **Acceso Programático / Reportes**:
  - Extracción de listados completos en CSV/JSON con un clic o vía API REST en modo solo lectura (`netbox-mcp`).

### 3.2 Procedimiento de Alta de Dispositivo (Onboarding)
- Flujo estandarizado paso a paso:
  1. Comprobar existencia del `Device Type` y `Manufacturer` (crear si es modelo nuevo).
  2. Seleccionar `Site`, `Location` (si aplica) y `Rack` (si es en CPD).
  3. Asignar `Device Role` (ej. `firewall`, `switch`, `access-point`, `router`).
  4. Introducir `Name` y `Serial Number` (siguiendo normativa de nomenclatura corporativa).
  5. Configurar interfaces (físicas, LAG, virtuales/VLANs).
  6. Asignar direcciones IP a interfaces y marcar la `Primary IPv4`.

### 3.3 Procedimiento de Baja de Dispositivo (Decommissioning)
- Flujo seguro de desaprovisionamiento:
  1. Cambio de estado a `Decommissioning` / `Offline` (mantiene histórico sin interferir en monitoreo).
  2. Liberación o reasignación de direcciones IP secundarias (liberación en IPAM si la IP vuelve al pool).
  3. Desconexión de cables lógicos/físicos en NetBox.
  4. Traslado a stock o estado `Inventory` o eliminación formal si el hardware se desecha.

### 3.4 Procedimiento de Reasignación de Dispositivo a Otra Sede / Ubicación
- Flujo de traslado:
  1. Actualización de `Site` y `Location` en el registro del dispositivo.
  2. Desvinculación de las VLANs de la sede de origen.
  3. Modificación del plan de direccionamiento IP (adaptar octeto de sede `10.XX.Y.Z` al nuevo bloque `/16`).
  4. Reasignación a los nuevos enlaces físicos/switches de la sede destino.

---

## 4. Automatizaciones e Integraciones Avanzadas

### 4.1 Automatización del Ciclo de Vida del Dispositivo (Reducción de Coste Operacional)
- **Problemática**: Un alta, baja o traslado manual en la GUI requiere entre 5 y 10 operaciones separadas (crear device, crear interfaces, vincular LAG, crear/asociar IPs, asignar primary IP, actualizar estado).
- **Solución Propuesta**:
  - **Scripts de Operación Unificada (NetBox Custom Scripts / CLI)**:
    - `deploy_spoke_device.py`: Recibe únicamente `[Nombre_Sede, Serial_Number, Modelo, IP_Base]` y ejecuta atómicamente toda la configuración (Device + LAG FortiLink + VLANs 10..90 + IPs + Primary IP).
    - `decommission_device.py`: Limpia asociaciones y archiva en un solo paso.
    - `relocate_device.py`: Calcula y aplica el cambio de direccionamiento y sede automáticamente.
  - **Webhooks y Event-Driven Automation**:
    - Disparo automático de tareas de notificación o aprovisionamiento al cambiar el estado de un equipo.

### 4.2 Barridos Periódicos y Conciliación Continua (AWS, Azure y Red Local)
- **Objetivo**: Descubrimiento proactivo y auditoría continua contra el "drift" de infraestructura (recursos creados fuera de proceso).
- **Arquitectura del Procedimiento**:
  1. **Colectores Automatizados (Scanners / Crawlers)**:
     - **Módulo Cloud (AWS & Azure)**:
       - AWS: Script Python (`boto3`) que consulta VPCs, Subnets, Route Tables, Transit Gateways, EC2s y Elastic IPs en las regiones activas.
       - Azure: Script Python (`azure-mgmt-network`, `azure-mgmt-compute`) que consulta VNets, Subredes y VMs.
     - **Módulo Red On-Premise**:
       - Inspección programada en FortiManager / FortiGate (tablas ARP, conmutación, interfaces).
  2. **Motor de Conciliación y Detección de Brechas**:
     - Compara los inventarios recolectados contra el estado actual en la API de NetBox.
     - Clasifica los hallazgos en tres categorías:
       - **Discrepancias de Atributos**: IP o nombre cambiado en la infraestructura real.
       - **Activos No Gestionados (Shadow IT)**: Subredes, instancias o interfaces que existen en la nube/red pero no están en NetBox.
       - **Activos Huérfanos**: Elementos registrados en NetBox que ya no existen en la infraestructura real.
  3. **Entregables Automatizados**:
     - Generación de informe en Markdown y JSON (`inputs/cloud_reconciliation_report.json`).
     - Propuesta de actualización lista para aplicar de forma asistida o con aprobación humana (Dry-Run).

### 4.3 Integración Bidireccional con Freshservice (CMDB / Gestión de Activos)
- **Objetivo**: Vincular los activos gestionados en NetBox con la CMDB de Freshservice para permitir asociar tickets de incidencias, cambios (`Changes`) y problemas (`Problems`) a los equipos de infraestructura.
- **Arquitectura de Sincronización**:
  1. **Fuente de Verdad**: NetBox actúa como la **Fuente de Verdad Técnica de Red**; Freshservice actúa como el **Registro de Activos de Servicio y Soporte**.
  2. **Mapeo de Entidades**:
     - NetBox `Device` (Firewall, Switch, Server, Router, AP) $\longleftrightarrow$ Freshservice `Asset` (Categoría: *Hardware / Network Device*).
     - NetBox `Serial Number` $\longleftrightarrow$ Freshservice `Serial Number` (clave de conciliación unívoca).
     - NetBox `Site` $\longleftrightarrow$ Freshservice `Location` (utilizando el catálogo ya sincronizado `inputs/fresh-locations.json`).
     - NetBox `Primary IP` $\longleftrightarrow$ Freshservice `IP Address`.
     - NetBox `Status` (`Active`, `Offline`, `Decommissioning`) $\longleftrightarrow$ Freshservice `Asset State` (`In Use`, `In Maintenance`, `Retired`).
  3. **Mecanismos de Sincronización**:
     - **NetBox Webhooks hacia n8n / Freshservice API**: Ante cualquier creación, actualización o baja en NetBox, emitir un webhook HTTP hacia un workflow que actualice el activo correspondiente en Freshservice vía API REST o MCP (`freshservice-mcp`).
     - **Script de Sincronización Programado (`sync_netbox_to_freshservice.py`)**: Barrido diario o bajo demanda que concilia altas y cambios de estado de forma masiva e idempotente.

---

## 5. Secuencia de Ejecución Completa: Optimización Nativa y Usabilidad

Hoja de ruta secuencial y ordenada para desplegar la optimización de NetBox (Opción 1), garantizando consistencia de datos, soporte de diagramación y entrega de asistentes operativos:

| Paso | Denominación | Acciones Clave | Entregables / Verificación |
| :--- | :--- | :--- | :--- |
| **Paso 0** | **Reorganización Estructural de Código (`src/`)** | • Separación de paquetes: `netbox_core/`, `netbox_ingest/` y `netbox_automation/`.<br>• Módulos de compatibilidad hacia atrás.<br>• Actualización de suite de pruebas unitarias. | • **COMPLETADO**: Tests pasando al 100% (`40 passed`).<br>• `src-layout` limpio conforme a gobernanza. |
| **Paso 1** | **Conectividad L1/L2 Mínima en Sede Piloto (Esplandiú)** | • Construcción del motor genérico reutilizable (`CableProvisioner` y `scripts/provision_cables.py`).<br>• Especificación declarativa en `inputs/cables_esplandiu.json`.<br>• Trazar troncal Firewall FortiLink (`FGT100-JES` $\longleftrightarrow$ `SW-ESPLAN-01`).<br>• Trazar 5 uplinks ISL entre switches distribuidos.<br>• Conectar interfaces PoE de APs y troncal de servidor `SVPROX`. | • **COMPLETADO / EJECUTADO**: 13 cables L1/L2 (`dcim/cables`) creados e interfaz `SVPROX:nic1` generada.<br>• Idempotencia y suite de tests validadas al 100%.<br>• Base de relaciones físicas lista previo al despliegue de plugins topológicos y usabilidad. |
| **Paso 2** | **Despliegue y Validación del Motor Topológico (`nextbox-ui-plugin`)** | • Incorporar `nextbox-ui-plugin>=1.0.7` en el Dockerfile (`edx-netbox-custom`).<br>• Hornear estáticos (`collectstatic`) y compilar para `linux/arm64`.<br>• Publicar imagen en ECR y actualizar ECS Task Definition (`netbox-prod`).<br>• Activar plugin en `extra.py` / `PLUGINS`. | • Menú Topología con motor NextUI operativo.<br>• Renderizado jerárquico verificado en Sede Esplandiú. |
| **Paso 3** | **Configuración de Vistas Persistentes (Saved Views & Bookmarks)** | • Crear *Saved Filters* predefinidos por Sede (Esplandiú, Hubs, Sedes críticas).<br>• Crear *Custom Links* en el menú de navegación para acceso inmediato a topologías y listados sin rellenar filtros manuales. | • Acceso a la topología y recursos de sede en 1 solo clic. |
| **Paso 4** | **Desarrollo de Asistentes Operativos (NetBox Custom Scripts)** | • Construir scripts GUI en `src/netbox_automation/custom_scripts/`: <br>  1. `DeviceWizard`: Alta atómica (Equipo + Interfaces + IP libre asignada).<br>  2. `IPAMQuickAllocate`: Reserva inmediata de próxima IP por VLAN.<br>  3. `DeviceLifecycle`: Reasignación de sede o baja/liberación limpia de IPs. | • Formularios nativos disponibles en `Customization > Scripts`.<br>• Reducción de 6 pantallas a 1 formulario por operativa. |
| **Paso 5** | **Pruebas de Aceptación, Documentación y Pase a Producción** | • Validación de flujos con usuarios finales.<br>• Comprobación de auditoría y compatibilidad con SSO Microsoft Entra ID.<br>• Actualización de manuales operativos (`docs/`). | • Pliego de requerimientos validado.<br>• Cierre y entrega del proyecto de optimización. |

