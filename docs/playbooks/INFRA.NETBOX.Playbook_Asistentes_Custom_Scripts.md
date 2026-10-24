<style>
  .doc-banner {
    background-color: #005F73;
    color: #FFFFFF;
    padding: 20px 24px;
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    border-radius: 2px;
    margin-bottom: 20px;
  }
  .doc-banner-subtitle {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    opacity: 0.9;
    margin-bottom: 6px;
    font-weight: 600;
  }
  .doc-banner-title {
    font-size: 1.75rem;
    font-weight: 700;
    margin-bottom: 6px;
    line-height: 1.2;
    letter-spacing: 0.3px;
  }
  .doc-banner-desc {
    font-size: 1rem;
    opacity: 0.95;
    font-weight: 400;
  }
  .doc-section-title {
    color: #005F73;
    font-size: 1.35rem;
    font-weight: 700;
    border-bottom: 2px solid #005F73;
    padding-bottom: 4px;
    margin-top: 28px;
    margin-bottom: 14px;
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }
  .doc-subsection-title {
    color: #0A9396;
    font-size: 1.15rem;
    font-weight: 700;
    margin-top: 20px;
    margin-bottom: 10px;
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }
  .doc-table {
    width: 100%;
    border-collapse: collapse;
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    font-size: 0.92rem;
    border: 1px solid #CBD5E1;
    margin: 16px 0;
  }
  .doc-table th {
    background-color: #E2E8F0;
    color: #000000 !important;
    padding: 10px 12px;
    text-align: left;
    font-weight: 700;
    border: 1px solid #CBD5E1;
  }
  .doc-table td {
    padding: 9px 12px;
    border: 1px solid #CBD5E1;
    vertical-align: top;
  }
  .doc-table tr:nth-child(odd) {
    background-color: #E8F4F8;
    color: #1F2937;
  }
  .doc-table tr:nth-child(even) {
    background-color: #FFFFFF;
    color: #1F2937;
  }
  .doc-callout-teal {
    background-color: #E8F4F8;
    border-left: 5px solid #005F73;
    padding: 12px 16px;
    margin: 16px 0;
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    border-radius: 0 4px 4px 0;
  }
  .doc-callout-title {
    color: #005F73;
    font-weight: 700;
    font-size: 0.9rem;
    text-transform: uppercase;
    margin-bottom: 4px;
    letter-spacing: 0.3px;
  }
  .doc-callout-body {
    color: #2D3748;
    font-size: 0.92rem;
    line-height: 1.5;
  }
</style>

<div class="doc-banner">
  <div class="doc-banner-subtitle">PLAYBOOK OPERATIVO Y PROCEDIMIENTO GUI</div>
  <div class="doc-banner-title">INFRA.NETBOX.Playbook_Asistentes_Custom_Scripts</div>
  <div class="doc-banner-desc">Guía de Operación de Asistentes Nativos en NetBox (DeviceWizard, IPAMQuickAllocate, DeviceLifecycle)</div>
</div>

---

<div class="doc-section-title">1. Resumen y Propósito</div>

Este playbook documenta la operativa de los asistentes unificados desarrollados como **NetBox Custom Scripts** (`extras.scripts.Script`). Su objetivo es reducir el coste operacional y eliminar errores humanos en la administración diaria de infraestructura, consolidando operaciones que requerían entre 5 y 10 pantallas en **un único formulario interactivo**.

<table class="doc-table">
  <thead>
    <tr>
      <th>Asistente</th>
      <th>Clase Python</th>
      <th>Función Operativa Principal</th>
      <th>Tiempo Ahorrado</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>1. Alta de Dispositivo</strong></td>
      <td><code>DeviceWizard</code></td>
      <td>Alta atómica de equipo, interfaz física y reserva/asignación de IP libre.</td>
      <td>De 6 pantallas a 1 formulario (~85% menos tiempo).</td>
    </tr>
    <tr>
      <td><strong>2. Reserva Rápida IPAM</strong></td>
      <td><code>IPAMQuickAllocate</code></td>
      <td>Localización y reserva de la próxima IP libre en una subred con opción de enlace a equipo.</td>
      <td>De 4 pasos de búsqueda a 1 clic.</td>
    </tr>
    <tr>
      <td><strong>3. Ciclo de Vida</strong></td>
      <td><code>DeviceLifecycle</code></td>
      <td>Reubicación de sede, baja operativa (decommissioning) o purga con desconexión limpia de cables e IPs.</td>
      <td>Cero registros huérfanos o cables colgando.</td>
    </tr>
  </tbody>
</table>

---

<div class="doc-section-title">2. Acceso y Uso en la GUI de NetBox</div>

Los asistentes se encuentran accesibles para usuarios autenticados en el menú lateral o superior de NetBox:
> **Ruta en NetBox**: `Customization` &gt; `Scripts` (o `Operations` &gt; `Scripts` según versión).

<div class="doc-callout-teal">
  <div class="doc-callout-title">REGLA DE ORO: EL CHECKBOX "COMMIT CHANGES"</div>
  <div class="doc-callout-body">
    Todos los scripts incluyen por defecto el checkbox <strong>"Commit changes" desmarcado</strong>.<br>
    - <strong>Desmarcado (Dry-Run)</strong>: Valida datos, comprueba IPs disponibles y simula el cambio sin alterar la base de datos.<br>
    - <strong>Marcado (Producción)</strong>: Aplica la transacción definitiva e inserta/modifica los registros reales.
  </div>
</div>

---

<div class="doc-section-title">3. Detalle Operativo por Asistente</div>

<div class="doc-subsection-title">3.1. Asistente 1: DeviceWizard (Alta Atómica de Dispositivo)</div>

Permite registrar un nuevo dispositivo físico o virtual asegurando la coherencia completa de relaciones.

1. **Campos del Formulario**:
   - **Sede (`site`)**: Desplegable con buscador AJAX de sedes registradas (ej. *Oficina Madrid - Esplandiú*).
   - **Rol (`device_role`)**: Desplegable de roles homologados (*Switch*, *Firewall*, *Access Point*, *Server*, etc.).
   - **Modelo (`device_type`)**: Selector del catálogo de modelos (ej. *FortiSwitch-148F*, *U6 Pro*).
   - **Nombre / Hostname (`name`)**: Identificador único corporativo (ej. `SW-ESPLAN-02`).
   - **Número de Serie (`serial`)** y **Asset Tag (`asset_tag`)**: Opcionales para inventario.
   - **Interfaz de Gestión (`interface_name`)**: Puerto físico principal (por defecto `eth0`).
   - **Subred IPAM (`prefix`)**: Si se selecciona, el asistente extrae automáticamente la primera IP libre disponible.
   - **IP Específica (`specific_ip`)**: Alternativa manual si no se desea cálculo automático.
   - **Estado Operativo (`status`)**: `active`, `planned` o `staged`.
2. **Ejecución y Resultados**:
   - Al ejecutar en Dry-Run, el log confirma la IP que se reservará y la interfaz asociada.
   - Al marcar "Commit changes", genera el enlace directo al nuevo `Device` con su `Primary IPv4` ya configurada.

---

<div class="doc-subsection-title">3.2. Asistente 2: IPAMQuickAllocate (Reserva Rápida de IPs)</div>

Diseñado para resolver solicitudes de red inmediatas (ej. reservar IP fija para una impresora, cámara o servidor).

1. **Campos del Formulario**:
   - **Prefijo / Subred (`prefix`)**: Selector del rango IPAM correspondiente a la sede/VLAN.
   - **Descripción / Propósito (`description`)**: Motivo de la asignación (ej. *Impresora Multifunción Planta 2*).
   - **Nombre DNS (`dns_name`)**: Opcional, para preconfigurar FQDN.
   - **Estado de la IP (`status`)**: `active`, `reserved` o `dhcp`.
   - **Dispositivo Destino (`device`)**: Opcional. Si se indica, asocia inmediatamente la IP a la interfaz del equipo.
   - **Designar como Primary IP (`set_as_primary`)**: Si el equipo no tenía IP primaria, la establece como tal.
2. **Control de Errores**:
   - Si la subred está al 100% de utilización, el script aborta limpiamente (`AbortScript`) avisando que el prefijo está agotado.

---

<div class="doc-subsection-title">3.3. Asistente 3: DeviceLifecycle (Ciclo de Vida y Bajas)</div>

Previene el "drift" de infraestructura y asegura que al dar de baja o mover un equipo no queden cables huérfanos o IPs asignadas a equipos inexistentes.

1. **Acciones Disponibles**:
   - **Reubicar en otra Sede (`relocate`)**: Actualiza la sede física del equipo. Permite retirar cables de la sede anterior y liberar direccionamiento IP obsoleto para que vuelva al pool libre de la sede de origen.
   - **Baja Operativa (`decommission`)**: Cambia el estado del dispositivo a `decommissioning` u `offline`, desconecta cables físicos y libera IPs, preservando el histórico del hardware y sus números de serie para auditoría.
   - **Baja Definitiva y Purga (`purge`)**: Elimina interfaces, conexiones y el registro del dispositivo de la base de datos de NetBox.
2. **Trazabilidad**:
   - El campo **Motivo del Cambio / Ticket ITSM (`comments`)** se adjunta al historial del dispositivo indicando fecha y justificación.

---

<div class="doc-section-title">4. Procedimiento de Despliegue en NetBox (ECS / Producción)</div>

Para que los scripts aparezcan en el menú `Customization > Scripts` del contenedor NetBox en producción:

1. **Estructura de Archivos en Contenedor**:
   - NetBox carga los scripts ubicados en su variable `SCRIPTS_ROOT` (por defecto `/opt/netbox/netbox/scripts/`).
2. **Inyección en Imagen Docker (`edx-netbox-custom`)**:
   - Los archivos de `src/netbox_automation/custom_scripts/` se copian al directorio de scripts durante el build de la imagen o mediante montaje de volumen persistente en la tarea ECS.
3. **Verificación de Carga**:
   - Acceder a NetBox con credenciales de administrador.
   - Navegar a `Customization > Scripts`.
   - Verificar la presencia de los tres módulos:
     1. *1. Alta de Dispositivo (Device Wizard)*
     2. *2. Reserva Rápida IPAM (Quick Allocate)*
     3. *3. Ciclo de Vida de Dispositivo (Lifecycle & Decommission)*
