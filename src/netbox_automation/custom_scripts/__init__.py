"""Scripts personalizados nativos de NetBox (extras.scripts.Script).

Contiene los asistentes de interfaz gráfica para optimización operativa:
- DeviceWizard: Alta atómica de dispositivo, interfaces e IP (dcim_01_device_wizard).
- DeviceLifecycle: Reubicación, baja operativa y purga segura (dcim_02_device_lifecycle).
- IPAMQuickAllocate: Reserva rápida de próxima IP por prefijo (ipam_01_quick_allocate).
"""

from netbox_automation.custom_scripts.dcim_01_device_wizard import DeviceWizard
from netbox_automation.custom_scripts.dcim_02_device_lifecycle import DeviceLifecycle
from netbox_automation.custom_scripts.ipam_01_quick_allocate import IPAMQuickAllocate

__all__ = [
    "DeviceWizard",
    "DeviceLifecycle",
    "IPAMQuickAllocate",
]
