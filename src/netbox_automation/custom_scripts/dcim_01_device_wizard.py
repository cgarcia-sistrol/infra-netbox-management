"""Asistente de Alta Atómica de Dispositivos en NetBox (DeviceWizard).

Permite dar de alta un equipo con su interfaz principal y dirección IP de gestión
en un único formulario atómico dentro de la interfaz web de NetBox (Customization > Scripts).
"""

from typing import Any, Dict

try:
    from extras.scripts import (
        Script,
        ObjectVar,
        ChoiceVar,
        StringVar,
        IPAddressVar,
        TextVar,
    )
    from dcim.models import Device, DeviceType, DeviceRole, Site, Interface
    from ipam.models import IPAddress, Prefix
    from utilities.exceptions import AbortScript
except ImportError:
    from netbox_automation.custom_scripts.base import (
        Script,
        ObjectVar,
        ChoiceVar,
        StringVar,
        IPAddressVar,
        TextVar,
        Device,
        DeviceType,
        DeviceRole,
        Site,
        Interface,
        IPAddress,
        Prefix,
        AbortScript,
    )


class DeviceWizard(Script):
    """Asistente para alta unificada de dispositivos con interfaz e IP."""

    class Meta:
        name = "[DCIM] Alta de Dispositivo (Device Wizard)"
        description = (
            "Aprovisionamiento atómico de dispositivo, interfaz física y reserva/asignación "
            "de la próxima IP libre en una sola operación."
        )
        commit_default = False

    site = ObjectVar(
        model=Site,
        label="Sede (Site)",
        description="Sede física donde se aloja el dispositivo.",
        query_params={"status": "active"},
    )
    device_role = ObjectVar(
        model=DeviceRole,
        label="Rol del Dispositivo",
        description="Función del dispositivo (ej. switch, firewall, access-point, server).",
    )
    device_type = ObjectVar(
        model=DeviceType,
        label="Modelo (Device Type)",
        description="Modelo de hardware homologado en el catálogo.",
    )
    device_name = StringVar(
        label="Nombre / Hostname",
        description="Identificador único del equipo (ej. SW-ESPLAN-02).",
    )
    serial = StringVar(
        label="Número de Serie",
        description="Número de serie físico del fabricante.",
        required=False,
    )
    asset_tag = StringVar(
        label="Etiqueta de Inventario (Asset Tag)",
        description="Identificador de inventario corporativo.",
        required=False,
    )
    interface_name = StringVar(
        label="Interfaz de Gestión",
        description="Nombre del puerto físico principal.",
        default="eth0",
    )
    prefix = ObjectVar(
        model=Prefix,
        label="Subred IPAM (Auto-asignación)",
        description="Prefijo desde el que reservar la próxima IP libre disponible.",
        required=False,
    )
    specific_ip = IPAddressVar(
        label="IP Específica (Manual)",
        description="Dirección IP manual (anula la búsqueda automática de IP libre).",
        required=False,
    )
    status = ChoiceVar(
        choices=[
            ("active", "Activo (Active)"),
            ("planned", "Planificado (Planned)"),
            ("staged", "En Preparación (Staged)"),
        ],
        default="active",
        label="Estado Operativo",
    )
    comments = TextVar(
        label="Comentarios / Observaciones",
        description="Detalles adicionales del aprovisionamiento.",
        required=False,
    )

    def run(self, data: Dict[str, Any], commit: bool) -> str:
        site = data["site"]
        role = data["device_role"]
        device_type = data["device_type"]
        name = (data.get("device_name") or data.get("name") or "").strip()
        serial = (data.get("serial") or "").strip()
        asset_tag = (data.get("asset_tag") or "").strip()
        interface_name = (data.get("interface_name") or "eth0").strip()
        prefix = data.get("prefix")
        specific_ip = data.get("specific_ip")
        status = data.get("status", "active")
        comments = (data.get("comments") or "").strip()

        if not name:
            self.log_failure("El campo 'Nombre / Hostname' no puede estar vacío.")
            raise AbortScript("El nombre del dispositivo es obligatorio.")

        mode_str = "PRODUCCIÓN" if commit else "SIMULACIÓN (DRY-RUN)"
        self.log_info(f"Iniciando asistente DeviceWizard en modo [{mode_str}] para '{name}' en '{site}'...")

        # 1. Instanciación de Dispositivo
        device = Device(
            name=name,
            site=site,
            device_type=device_type,
            status=status,
            serial=serial,
            asset_tag=asset_tag,
            comments=comments,
        )
        if hasattr(device, "role"):
            device.role = role
        if hasattr(device, "device_role"):
            device.device_role = role

        if commit:
            device.save()
        self.log_success(f"Dispositivo '{name}' (Rol: {role}, Modelo: {device_type}) preparado correctamente.")

        # 2. Creación de Interfaz de Gestión
        interface = Interface(
            device=device,
            name=interface_name,
            type="1000base-t",
            mgmt_only=True,
            description=f"Interfaz principal de gestión para {name}",
        )
        if commit:
            interface.save()
        self.log_success(f"Interfaz de gestión '{interface_name}' configurada.")

        # 3. Determinación de IP (Manual vs Auto-asignada)
        ip_obj = None
        if specific_ip:
            ip_str = str(specific_ip).strip()
            self.log_info(f"Asignando IP manual configurada: {ip_str}")
            ip_obj = IPAddress(
                address=ip_str,
                status="active",
                description=f"IP de gestión para {name}",
            )
            if commit:
                ip_obj.save()
        elif prefix:
            self.log_info(f"Buscando próxima IP disponible en el prefijo {prefix}...")
            # NetBox API / Model get_available_ips()
            available_ips = []
            if hasattr(prefix, "get_available_ips"):
                available_ips = prefix.get_available_ips()

            if not available_ips:
                self.log_failure(f"El prefijo {prefix} no tiene direcciones IP libres disponibles.")
                raise AbortScript(f"Prefijo {prefix} agotado.")

            next_ip = available_ips[0]
            mask = str(prefix).split("/")[-1] if "/" in str(prefix) else "24"
            ip_str = f"{next_ip}/{mask}"
            self.log_info(f"Auto-reservada próxima IP libre: {ip_str}")
            ip_obj = IPAddress(
                address=ip_str,
                status="active",
                description=f"IP de gestión para {name}",
            )
            if commit:
                ip_obj.save()

        # 4. Vinculación de IP a la Interfaz y como Primary IPv4
        if ip_obj:
            ip_obj.assigned_object = interface
            if commit:
                ip_obj.save()
                device.primary_ip4 = ip_obj
                device.save()
            self.log_success(f"Dirección IP {ip_obj.address} vinculada como Primary IPv4 a '{name}'.")

        summary = (
            f"Alta completada exitosamente:\n"
            f"- Dispositivo: {name} (ID: {getattr(device, 'id', 'dry-run')})\n"
            f"- Sede: {site}\n"
            f"- Interfaz: {interface_name}\n"
            f"- IP Gestión: {getattr(ip_obj, 'address', 'Ninguna asignada')}\n"
            f"- Modo: {mode_str}"
        )
        return summary
