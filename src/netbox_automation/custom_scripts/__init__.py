"""Scripts personalizados nativos de NetBox (extras.scripts.Script).

Contiene los asistentes de interfaz gráfica para optimización operativa:
- DeviceWizard: Alta atómica de dispositivo, interfaces e IP.
- IPAMQuickAllocate: Reserva rápida de próxima IP por prefijo.
- DeviceLifecycle: Reubicación, baja operativa y purga segura.
"""

from netbox_automation.custom_scripts.device_wizard import DeviceWizard
from netbox_automation.custom_scripts.ipam_quick_allocate import IPAMQuickAllocate
from netbox_automation.custom_scripts.device_lifecycle import DeviceLifecycle

__all__ = [
    "DeviceWizard",
    "IPAMQuickAllocate",
    "DeviceLifecycle",
]
