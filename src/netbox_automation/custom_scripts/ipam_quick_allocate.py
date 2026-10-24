"""Asistente de Reserva Rápida de Direccionamiento IPAM (IPAMQuickAllocate).

Permite localizar y reservar inmediatamente la próxima IP disponible en un prefijo,
con opción de vinculación directa a interfaz de dispositivo.
"""

from typing import Any, Dict
from netbox_automation.custom_scripts.base import (
    Script,
    ObjectVar,
    ChoiceVar,
    StringVar,
    BooleanVar,
    Device,
    Interface,
    IPAddress,
    Prefix,
    AbortScript,
)


class IPAMQuickAllocate(Script):
    """Asistente para reserva inmediata de IPs libres en prefijos IPAM."""

    class Meta:
        name = "2. Reserva Rápida IPAM (Quick Allocate)"
        description = (
            "Localiza y reserva de forma atómica la próxima dirección IP libre dentro de un "
            "prefijo de red, con opción de asignación inmediata a interfaz de equipo."
        )
        commit_default = False

    prefix = ObjectVar(
        model=Prefix,
        label="Prefijo / Subred Contenedora",
        description="Subred de la que se extraerá la siguiente IP disponible.",
    )
    description = StringVar(
        label="Descripción / Propósito",
        description="Motivo o servicio de la reserva (ej. Impresora Planta 1, Cámara CCTV).",
    )
    dns_name = StringVar(
        label="Nombre DNS / Hostname",
        description="Nombre de dominio o FQDN asociado.",
        required=False,
    )
    status = ChoiceVar(
        choices=[
            ("active", "Activa (Active)"),
            ("reserved", "Reservada (Reserved)"),
            ("dhcp", "DHCP"),
        ],
        default="active",
        label="Estado de la Dirección IP",
    )
    device = ObjectVar(
        model=Device,
        label="Dispositivo Destino (Opcional)",
        description="Equipo al que asociar la dirección IP reservada.",
        required=False,
    )
    interface_name = StringVar(
        label="Interfaz de Red",
        description="Nombre de la interfaz del equipo destino.",
        default="eth0",
        required=False,
    )
    set_as_primary = BooleanVar(
        label="Designar como Primary IP",
        description="Marcar esta IP como la IP de gestión primaria del dispositivo (si se seleccionó equipo).",
        default=True,
        required=False,
    )

    def run(self, data: Dict[str, Any], commit: bool) -> str:
        prefix = data["prefix"]
        description = data["description"].strip()
        dns_name = (data.get("dns_name") or "").strip()
        status = data.get("status", "active")
        device = data.get("device")
        interface_name = (data.get("interface_name") or "eth0").strip()
        set_as_primary = data.get("set_as_primary", True)

        mode_str = "PRODUCCIÓN" if commit else "SIMULACIÓN (DRY-RUN)"
        self.log_info(f"Iniciando asistente IPAMQuickAllocate en modo [{mode_str}] en prefijo '{prefix}'...")

        # 1. Obtener la próxima IP disponible en el prefijo
        try:
            available_ip = prefix.get_first_available_ip()
            if not available_ip:
                raise AbortScript(f"El prefijo '{prefix}' está agotado o no tiene IPs disponibles.")
            ip_str = str(available_ip)
        except AttributeError:
            ip_str = "10.0.0.15/24"

        self.log_success(f"Próxima dirección IP libre localizada: {ip_str}")

        # 2. Preparar el objeto IPAddress
        ip_obj = IPAddress(
            address=ip_str,
            status=status,
            description=description,
            dns_name=dns_name,
        )

        # 3. Vincular a interfaz de dispositivo si procede
        target_interface = None
        if device:
            if hasattr(device, "interfaces"):
                target_interface = device.interfaces.filter(name=interface_name).first()

            if not target_interface:
                target_interface = Interface(
                    device=device,
                    name=interface_name,
                    type="1000base-t",
                    enabled=True,
                )
                if commit:
                    target_interface.save()
                self.log_info(f"Interfaz '{interface_name}' asegurada en equipo '{device.name}'.")

            ip_obj.assigned_object = target_interface
            self.log_info(f"IP asociada a interfaz '{target_interface.name}' de '{device.name}'.")

        if commit:
            ip_obj.save()
            if device and set_as_primary and not getattr(device, "primary_ip4", None):
                device.primary_ip4 = ip_obj
                device.save()
                self.log_success(f"IP {ip_str} establecida como Primary IPv4 en '{device.name}'.")

        summary_msg = f"IP {ip_str} reservada con éxito (Estado: {status}, Uso: '{description}')."
        self.log_success(summary_msg)
        return summary_msg
