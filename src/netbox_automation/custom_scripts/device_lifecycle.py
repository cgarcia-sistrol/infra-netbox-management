"""Asistente de Ciclo de Vida de Dispositivos en NetBox (DeviceLifecycle).

Permite reubicar equipos entre sedes, gestionar bajas operativas o purgas definitivas
con liberación automatizada de cables y direcciones IP.
"""

from typing import Any, Dict
from netbox_automation.custom_scripts.base import (
    Script,
    ObjectVar,
    ChoiceVar,
    BooleanVar,
    TextVar,
    Device,
    Site,
    Cable,
    IPAddress,
    AbortScript,
)


class DeviceLifecycle(Script):
    """Asistente para traslados de sede, bajas operativas y purga de equipos."""

    class Meta:
        name = "3. Ciclo de Vida de Dispositivo (Lifecycle & Decommission)"
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
        label="Nueva Sede (Solo para Reubicación)",
        description="Sede física de destino si la acción seleccionada es Reubicar.",
        required=False,
    )
    disconnect_cables = BooleanVar(
        label="Desconectar Cableado Físico",
        description="Retira automáticamente los cables conectados a los puertos de este equipo.",
        default=True,
        required=False,
    )
    release_ips = BooleanVar(
        label="Liberar / Desvincular Direcciones IP",
        description="Desasocia las direcciones IP asignadas a las interfaces para devolverlas al pool.",
        default=True,
        required=False,
    )
    comments = TextVar(
        label="Motivo del Cambio / Ticket ITSM",
        description="Referencia de cambio o justificación para auditoría.",
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
        self.log_info(f"Iniciando asistente DeviceLifecycle [{action.upper()}] en modo [{mode_str}] para '{device.name}'...")

        # 1. Validaciones previas
        if action == "relocate":
            if not new_site:
                raise AbortScript("La acción de reubicación requiere seleccionar obligatoriamente una 'Nueva Sede'.")
            if getattr(device, "site", None) == new_site:
                self.log_warning(f"El equipo '{device.name}' ya se encuentra asignado a la sede '{new_site}'.")

        # 2. Desconexión de cables si procede
        if disconnect_cables:
            cables_removed = 0
            if hasattr(device, "interfaces"):
                for intf in device.interfaces.all():
                    if getattr(intf, "cable", None):
                        cables_removed += 1
                        if commit:
                            intf.cable.delete()
            self.log_info(f"Cables físicos desconectados/retirados: {cables_removed}.")

        # 3. Liberación de IPs asociadas
        if release_ips:
            if getattr(device, "primary_ip4", None):
                self.log_info(f"Desvinculando Primary IP ({device.primary_ip4}) de '{device.name}'.")
                if commit:
                    device.primary_ip4 = None
                    device.save()

            if hasattr(device, "interfaces"):
                for intf in device.interfaces.all():
                    if hasattr(intf, "ip_addresses"):
                        for ip in intf.ip_addresses.all():
                            self.log_info(f"Liberando IP {ip.address} de interfaz {intf.name}.")
                            if commit:
                                ip.assigned_object = None
                                ip.save()

        # 4. Ejecución según acción
        summary_msg = ""
        if action == "relocate":
            old_site = getattr(device, "site", "Desconocido")
            device.site = new_site
            if comments:
                prev_comments = getattr(device, "comments", "") or ""
                device.comments = f"{prev_comments}\n[Reubicación de {old_site} a {new_site}]: {comments}".strip()
            if commit:
                device.save()
            summary_msg = f"Dispositivo '{device.name}' trasladado con éxito a sede '{new_site}'."
            self.log_success(summary_msg)

        elif action == "decommission":
            device.status = "decommissioning"
            if comments:
                prev_comments = getattr(device, "comments", "") or ""
                device.comments = f"{prev_comments}\n[Baja Operativa]: {comments}".strip()
            if commit:
                device.save()
            summary_msg = f"Dispositivo '{device.name}' marcado en estado 'decommissioning' (baja operativa)."
            self.log_success(summary_msg)

        elif action == "purge":
            dev_name = device.name
            if commit:
                if hasattr(device, "interfaces"):
                    for intf in device.interfaces.all():
                        intf.delete()
                device.delete()
            summary_msg = f"Dispositivo '{dev_name}' eliminado y purgado definitivamente del inventario."
            self.log_success(summary_msg)

        return summary_msg
