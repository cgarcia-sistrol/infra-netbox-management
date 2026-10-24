"""Definiciones base y puente de compatibilidad para NetBox Custom Scripts.

Si se ejecuta dentro del entorno NetBox (producción), importa directamente
los modelos y clases nativas de NetBox y Django.
Si se ejecuta fuera de NetBox (tests unitarios locales), proporciona shims ligeros
para permitir pruebas sin dependencias de infraestructura.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from extras.scripts import (  # type: ignore
        Script,
        ObjectVar,
        ChoiceVar,
        StringVar,
        IPAddressVar,
        BooleanVar,
        TextVar,
        IntegerVar,
        MultiObjectVar,
    )
    from dcim.models import Device, DeviceType, DeviceRole, Site, Interface, Cable  # type: ignore
    from ipam.models import IPAddress, Prefix, VLAN  # type: ignore
    from utilities.exceptions import AbortScript  # type: ignore
    IS_NETBOX_ENV = True

except ImportError:
    IS_NETBOX_ENV = False

    class AbortScript(Exception):  # type: ignore
        """Excepción para abortar un script limpiamente."""
        pass

    class ScriptVariable:
        def __init__(
            self,
            label: Optional[str] = None,
            description: Optional[str] = None,
            required: bool = True,
            default: Any = None,
        ):
            self.label = label
            self.description = description
            self.required = required
            self.default = default

    class ObjectVar(ScriptVariable):  # type: ignore
        def __init__(
            self,
            model: Any,
            label: Optional[str] = None,
            description: Optional[str] = None,
            required: bool = True,
            default: Any = None,
            query_params: Optional[Dict[str, Any]] = None,
            display_field: Optional[str] = None,
        ):
            super().__init__(label=label, description=description, required=required, default=default)
            self.model = model
            self.query_params = query_params or {}
            self.display_field = display_field

    class MultiObjectVar(ScriptVariable):  # type: ignore
        def __init__(
            self,
            model: Any,
            label: Optional[str] = None,
            description: Optional[str] = None,
            required: bool = True,
            default: Any = None,
            query_params: Optional[Dict[str, Any]] = None,
        ):
            super().__init__(label=label, description=description, required=required, default=default)
            self.model = model
            self.query_params = query_params or {}

    class StringVar(ScriptVariable):  # type: ignore
        def __init__(
            self,
            label: Optional[str] = None,
            description: Optional[str] = None,
            required: bool = True,
            default: Any = None,
            regex: Optional[str] = None,
        ):
            super().__init__(label=label, description=description, required=required, default=default)
            self.regex = regex

    class TextVar(ScriptVariable):  # type: ignore
        pass

    class IntegerVar(ScriptVariable):  # type: ignore
        def __init__(
            self,
            label: Optional[str] = None,
            description: Optional[str] = None,
            required: bool = True,
            default: Any = None,
            min_value: Optional[int] = None,
            max_value: Optional[int] = None,
        ):
            super().__init__(label=label, description=description, required=required, default=default)
            self.min_value = min_value
            self.max_value = max_value

    class BooleanVar(ScriptVariable):  # type: ignore
        pass

    class ChoiceVar(ScriptVariable):  # type: ignore
        def __init__(
            self,
            choices: List[Union[Tuple[str, str], str]],
            label: Optional[str] = None,
            description: Optional[str] = None,
            required: bool = True,
            default: Any = None,
        ):
            super().__init__(label=label, description=description, required=required, default=default)
            self.choices = choices

    class IPAddressVar(ScriptVariable):  # type: ignore
        pass

    class IPNetworkVar(ScriptVariable):  # type: ignore
        pass

    class MockModelBase:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", 1)
            for k, v in kwargs.items():
                setattr(self, k, v)
            self._saved = False
            self._deleted = False

        def save(self):
            self._saved = True
            return self

        def delete(self):
            self._deleted = True

        def __str__(self):
            return getattr(self, "name", getattr(self, "model", str(self.id)))

    class Site(MockModelBase):  # type: ignore
        name: str = "Mock Site"
        slug: str = "mock-site"
        status: str = "active"

    class DeviceRole(MockModelBase):  # type: ignore
        name: str = "Mock Role"
        slug: str = "mock-role"

    class DeviceType(MockModelBase):  # type: ignore
        model: str = "Mock Model"
        slug: str = "mock-model"
        manufacturer: Any = None

    class Device(MockModelBase):  # type: ignore
        name: str = "Mock-Device"
        site: Any = None
        role: Any = None
        device_role: Any = None
        device_type: Any = None
        serial: str = ""
        asset_tag: str = ""
        status: str = "active"
        primary_ip4: Any = None
        comments: str = ""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            if "role" in kwargs and "device_role" not in kwargs:
                self.device_role = kwargs["role"]
            elif "device_role" in kwargs and "role" not in kwargs:
                self.role = kwargs["device_role"]

    class Interface(MockModelBase):  # type: ignore
        device: Any = None
        name: str = "eth0"
        type: str = "1000base-t"
        enabled: bool = True
        cable: Any = None

    class IPAddress(MockModelBase):  # type: ignore
        address: str = "192.0.2.1/24"
        status: str = "active"
        assigned_object: Any = None
        description: str = ""
        dns_name: str = ""

    class Prefix(MockModelBase):  # type: ignore
        prefix: str = "10.0.0.0/24"
        site: Any = None
        status: str = "active"
        _next_ip: Optional[str] = "10.0.0.10/24"

        def get_first_available_ip(self):
            return self._next_ip

    class VLAN(MockModelBase):  # type: ignore
        vid: int = 10
        name: str = "VLAN_10"
        site: Any = None

    class Cable(MockModelBase):  # type: ignore
        termination_a: Any = None
        termination_b: Any = None
        status: str = "connected"

    class Script:  # type: ignore
        class Meta:
            name = "Base Script"
            description = "Base script mock"

        def __init__(self):
            self.logs: List[Dict[str, str]] = []

        def log_info(self, message: str):
            self.logs.append({"level": "info", "message": str(message)})

        def log_success(self, message: str):
            self.logs.append({"level": "success", "message": str(message)})

        def log_warning(self, message: str):
            self.logs.append({"level": "warning", "message": str(message)})

        def log_failure(self, message: str):
            self.logs.append({"level": "failure", "message": str(message)})

        def run(self, data: Dict[str, Any], commit: bool) -> Any:
            raise NotImplementedError
