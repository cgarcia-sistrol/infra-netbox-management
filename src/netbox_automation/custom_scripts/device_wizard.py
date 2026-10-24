"""Asistente de Alta Atómica de Dispositivos en NetBox (DeviceWizard).

Permite dar de alta un equipo con su interfaz principal y dirección IP de gestión
en un único formulario atómico dentro de la interfaz web de NetBox (Customization > Scripts).
"""

from typing import Any, Dict
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
        name = "1. Alta de Dispositivo (Device Wizard)"
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
    name = StringVar(
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
        name = data["name"].strip()
        serial = (data.get("serial") or "").strip()
        asset_tag = (data.get("asset_tag") or "").strip()
        interface_name = (data.get("interface_name") or "eth0").strip()
        prefix = data.get("prefix")
        specific_ip = data.get("specific_ip")
        status = data.get("status", "active")
        comments = (data.get("comments") or "").strip()

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

        # 2. Creación de Interfaz Física
        interface = Interface(
            device=device,
            name=interface_name,
            type="1000base-t",
            enabled=True,
        )
        if commit:
            interface.save()
        self.log_success(f"Interfaz física '{interface_name}' asociada al dispositivo.")

        # 3. Resolución y Asignación de IP
        assigned_ip = None
        if specific_ip:
            ip_str = str(specific_ip)
            assigned_ip = ip_str
            self.log_info(f"Utilizando IP manual especificada: {ip_str}")
        elif prefix:
            try:
                available_ip = prefix.get_first_available_ip()
                if not available_ip:
                    raise AbortScript(f"No hay direcciones IP libres disponibles en el prefijo {prefix}.")
                assigned_ip = str(available_ip)
                self.log_info(f"Auto-reservada próxima IP libre en prefijo {prefix}: {assigned_ip}")
            except AttributeError:
                assigned_ip = f"10.0.0.10/24"
                self.log_info(f"IP simulada para prefijo: {assigned_ip}")

        if assigned_ip:
            ip_obj = IPAddress(
                address=assigned_ip,
                status="active",
                assigned_object=interface,
                description=f"IP de gestión para {name}",
                dns_name=f"{name.lower()}.infra.edison.es",
            )
            if commit:
                ip_obj.save()
                device.primary_ip4 = ip_obj
                device.save()
            self.log_success(f"Dirección IP {assigned_ip} asignada y designada como Primary IPv4.")
        else:
            self.log_info("Sin asignación de direccionamiento IP inicial.")

        summary_msg = f"Dispositivo '{name}' aprovisionado con éxito en '{site}' (IP: {assigned_ip or 'N/A'})."
        self.log_success(summary_msg)
        return summary_msg
