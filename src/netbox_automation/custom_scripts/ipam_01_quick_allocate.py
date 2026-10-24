"""Asistente de Reserva Rápida IPAM en NetBox (IPAMQuickAllocate).

Permite reservar la próxima dirección IP libre dentro de un prefijo de red
e integrarla directamente a una interfaz física/virtual de dispositivo.
"""

from typing import Any, Dict

try:
    from extras.scripts import (
        Script,
        ObjectVar,
        ChoiceVar,
        StringVar,
        BooleanVar,
    )
    from dcim.models import Device, Interface
    from ipam.models import IPAddress, Prefix
    from utilities.exceptions import AbortScript
except ImportError:
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
        name = "1. Reserva Rápida IPAM (Quick Allocate)"
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
    purpose = StringVar(
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
        label="Estado de la IP",
    )
    device = ObjectVar(
        model=Device,
        label="Dispositivo Destino (Opcional)",
        description="Equipo al que se vinculará la dirección IP.",
        required=False,
    )
    interface_name = StringVar(
        label="Nombre de Interfaz",
        description="Puerto del dispositivo al que asociar la IP (si se seleccionó Dispositivo).",
        default="eth0",
        required=False,
    )
    set_as_primary = BooleanVar(
        label="Establecer como IP Primaria",
        description="Marca esta IP como la dirección IPv4 principal del equipo.",
        default=False,
    )

    def run(self, data: Dict[str, Any], commit: bool) -> str:
        prefix = data["prefix"]
        purpose = (data.get("purpose") or data.get("description") or "").strip()
        dns_name = (data.get("dns_name") or "").strip()
        status = data.get("status", "active")
        device = data.get("device")
        interface_name = (data.get("interface_name") or "eth0").strip()
        set_as_primary = data.get("set_as_primary", False)

        mode_str = "PRODUCCIÓN" if commit else "SIMULACIÓN (DRY-RUN)"
        self.log_info(f"Iniciando asistente IPAMQuickAllocate en modo [{mode_str}] sobre prefijo {prefix}...")

        # 1. Obtener siguiente IP libre
        available_ips = []
        if hasattr(prefix, "get_available_ips"):
            available_ips = prefix.get_available_ips()

        if not available_ips:
            self.log_failure(f"El prefijo {prefix} no tiene direcciones IP disponibles.")
            raise AbortScript(f"Prefijo {prefix} sin direcciones disponibles.")

        next_ip = available_ips[0]
        mask = str(prefix).split("/")[-1] if "/" in str(prefix) else "24"
        ip_str = f"{next_ip}/{mask}"
        self.log_info(f"Localizada próxima IP libre: {ip_str}")

        # 2. Instanciar IP
        ip_obj = IPAddress(
            address=ip_str,
            status=status,
            description=purpose,
            dns_name=dns_name,
        )
        if commit:
            ip_obj.save()
        self.log_success(f"Dirección IP {ip_str} reservada con propósito: '{purpose}'.")

        # 3. Vincular a Dispositivo e Interfaz si aplica
        assigned_iface = None
        if device:
            self.log_info(f"Vinculando {ip_str} al dispositivo '{device.name}'...")
            # Buscar si interfaz existe o crearla
            if hasattr(device, "interfaces") and hasattr(device.interfaces, "all"):
                for iface in device.interfaces.all():
                    if iface.name == interface_name:
                        assigned_iface = iface
                        break

            if not assigned_iface:
                self.log_info(f"Creando interfaz '{interface_name}' en '{device.name}'...")
                assigned_iface = Interface(
                    device=device,
                    name=interface_name,
                    type="1000base-t",
                )
                if commit:
                    assigned_iface.save()

            ip_obj.assigned_object = assigned_iface
            if commit:
                ip_obj.save()
                if set_as_primary:
                    device.primary_ip4 = ip_obj
                    device.save()
                    self.log_success(f"Asignada como IP primaria a {device.name}.")

        summary = (
            f"Reserva de IP completada:\n"
            f"- Dirección: {ip_str}\n"
            f"- Prefijo: {prefix}\n"
            f"- Propósito: {purpose}\n"
            f"- Dispositivo: {device.name if device else 'Ninguno'}\n"
            f"- Modo: {mode_str}"
        )
        return summary
