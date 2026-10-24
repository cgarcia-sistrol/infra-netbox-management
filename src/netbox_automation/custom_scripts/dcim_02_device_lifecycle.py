"""Asistente de Ciclo de Vida y Baja de Dispositivos (DeviceLifecycle).

Permite gestionar reubicaciones de sede, bajas operativas controladas
y desmantelamientos físicos con liberación limpia de IPs y cableado.
"""

from typing import Any, Dict

try:
    from extras.scripts import (
        Script,
        ObjectVar,
        ChoiceVar,
        BooleanVar,
        TextVar,
    )
    from dcim.models import Device, Site
    from ipam.models import IPAddress
    from utilities.exceptions import AbortScript
except ImportError:
    from netbox_automation.custom_scripts.base import (
        Script,
        ObjectVar,
        ChoiceVar,
        BooleanVar,
        TextVar,
        Device,
        Site,
        IPAddress,
        AbortScript,
    )


class DeviceLifecycle(Script):
    """Asistente para traslados de sede, bajas operativas y purga de equipos."""

    class Meta:
        name = "2. Ciclo de Vida de Dispositivo (Lifecycle & Decommission)"
        description = (
            "Operaciones seguras de ciclo de vida: Reubicación entre sedes, baja operativa "
            "controlada (decommissioning) o desmantelamiento físico con liberación limpia de IPs y cableado."
        )
        commit_default = False

    action = ChoiceVar(
        choices=[
            ("relocate", "Reubicar en otra Sede (Relocate)"),
            ("decommission", "Baja Operativa (Decommissioning / Offline)"),
            ("purge", "Baja Definitiva y Purga del Registro"),
        ],
        default="relocate",
        label="Acción de Ciclo de Vida",
    )
    device = ObjectVar(
        model=Device,
        label="Dispositivo Objetivo",
        description="Equipo sobre el cual se aplicará el cambio operativo.",
    )
    new_site = ObjectVar(
        model=Site,
        label="Nueva Sede (Reubicación)",
        description="Requerido si la acción es 'Reubicar en otra Sede'.",
        required=False,
    )
    disconnect_cables = BooleanVar(
        label="Desconectar Cableado Físico",
        description="Elimina todas las conexiones de cables asociadas a sus puertos.",
        default=True,
    )
    release_ips = BooleanVar(
        label="Liberar Direcciones IP",
        description="Desvincula y libera las IPs asociadas a las interfaces del equipo.",
        default=True,
    )
    comments = TextVar(
        label="Motivo / Ticket de Cambio",
        description="Referencia de cambio (ej. Ticket INC-4921 / Desmantelamiento CPD).",
        required=False,
    )

    def run(self, data: Dict[str, Any], commit: bool) -> str:
        action = data["action"]
        device = data["device"]
        new_site = data.get("new_site")
        disconnect_cables = data.get("disconnect_cables", True)
        release_ips = data.get("release_ips", True)
        comments = (data.get("comments") or "").strip()

        mode_str = "PRODUCCIÓN" if commit else "SIMULACIÓN (DRY-RUN)"
        self.log_info(f"Iniciando Asistente DeviceLifecycle en modo [{mode_str}] para dispositivo '{device}'...")

        if action == "relocate":
            if not new_site:
                self.log_failure("Para reubicar un dispositivo es obligatorio seleccionar la 'Nueva Sede'.")
                raise AbortScript("Nueva sede no especificada.")

            old_site = device.site
            self.log_info(f"Reubicando '{device.name}' desde '{old_site}' hacia '{new_site}'...")
            device.site = new_site
            if comments:
                device.comments = f"{getattr(device, 'comments', '')}\n[Traslado]: {comments}".strip()

            if commit:
                device.save()
            self.log_success(f"Dispositivo reubicado en '{new_site}'.")

            if disconnect_cables:
                self._handle_cables(device, commit)
            if release_ips:
                self._handle_ips(device, commit)

            return f"Dispositivo '{device.name}' trasladado con éxito a '{new_site}' [{mode_str}]."

        elif action == "decommission":
            self.log_info(f"Cambiando estado de '{device.name}' a 'decommissioning'...")
            device.status = "decommissioning"
            if comments:
                device.comments = f"{getattr(device, 'comments', '')}\n[Decommission]: {comments}".strip()

            if commit:
                device.save()
            self.log_success(f"Estado de '{device.name}' actualizado a 'decommissioning'.")

            if disconnect_cables:
                self._handle_cables(device, commit)
            if release_ips:
                self._handle_ips(device, commit)

            return f"Dispositivo '{device.name}' marcado en baja operativa (decommissioning) [{mode_str}]."

        elif action == "purge":
            self.log_warning(f"¡ATENCIÓN! Se solicita eliminación completa del dispositivo '{device.name}'.")
            if disconnect_cables:
                self._handle_cables(device, commit)
            if release_ips:
                self._handle_ips(device, commit)

            if commit:
                device.delete()
            self.log_success(f"Dispositivo '{device.name}' eliminado satisfactoriamente del inventario.")
            return f"Dispositivo '{device.name}' purgado definitivamente de NetBox [{mode_str}]."

        else:
            raise AbortScript(f"Acción '{action}' no reconocida.")

    def _handle_cables(self, device: Any, commit: bool) -> None:
        """Desconecta cables conectados a interfaces del equipo."""
        interfaces = getattr(device, "interfaces", None)
        if interfaces and hasattr(interfaces, "all"):
            for iface in interfaces.all():
                cable = getattr(iface, "cable", None)
                if cable:
                    self.log_info(f"Desconectando cable de interfaz '{iface.name}'...")
                    if commit:
                        cable.delete()

    def _handle_ips(self, device: Any, commit: bool) -> None:
        """Libera IPs vinculadas a interfaces del equipo."""
        interfaces = getattr(device, "interfaces", None)
        if interfaces and hasattr(interfaces, "all"):
            for iface in interfaces.all():
                ip_addresses = getattr(iface, "ip_addresses", None)
                if ip_addresses and hasattr(ip_addresses, "all"):
                    for ip in ip_addresses.all():
                        self.log_info(f"Liberando dirección IP '{ip.address}' de '{iface.name}'...")
                        if commit:
                            ip.assigned_object = None
                            ip.status = "deprecated"
                            ip.save()
