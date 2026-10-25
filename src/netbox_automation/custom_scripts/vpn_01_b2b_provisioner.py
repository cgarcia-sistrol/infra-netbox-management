"""Asistente Operativo Universal para Aprovisionamiento de VPNs B2B y NAT en NetBox.

Permite a los operadores y técnicos de soporte desplegar y documentar de forma
transaccional, idempotente y estandarizada cualquier interconexión VPN Site-to-Site,
soportando:
- Topología Single-Hub (Madrid CPD o JESP) y Dual-Hub Redundante.
- Terminadores remotos principales y secundarios (Dual-Peer).
- Todo el abanico de escenarios NAT (Sin NAT, SNAT Local, NAT por Contraparte y DNAT Local).
- Etiquetado dinámico cruzado (vpn:<slug-tunel>) en túneles, prefijos e IPs.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from extras.scripts import (
        Script,
        StringVar,
        ChoiceVar,
        BooleanVar,
        TextVar,
    )
    from utilities.exceptions import AbortScript
    from ipam.models import Prefix, IPAddress, VRF, Role
    from tenancy.models import Tenant
    from extras.models import Tag
    from dcim.models import Device, Interface
    try:
        from django.contrib.contenttypes.models import ContentType
    except ImportError:
        ContentType = None
    try:
        from vpn.models import Tunnel, TunnelGroup, TunnelTermination, IPSecProfile
    except ImportError:
        Tunnel = None
        TunnelGroup = None
        TunnelTermination = None
        IPSecProfile = None
    IS_NETBOX_ENV = True
except ImportError:
    from netbox_automation.custom_scripts.base import (
        Script,
        StringVar,
        ChoiceVar,
        BooleanVar,
        TextVar,
        AbortScript,
        Prefix,
        IPAddress,
        VRF,
        Role,
        Tenant,
        Tag,
        Device,
        Interface,
        Tunnel,
        TunnelGroup,
        TunnelTermination,
        IPSecProfile,
        ContentType,
    )
    IS_NETBOX_ENV = False


def slugify(text: str) -> str:
    """Convierte una cadena a slug alfanumérico en minúsculas."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def clean_lines(text: Optional[str]) -> List[str]:
    """Limpia y divide un bloque de texto en líneas no vacías."""
    if not text:
        return []
    lines = [line.strip() for line in text.strip().splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def parse_traffic_selectors(lines: List[str]) -> List[Dict[str, str]]:
    """Parsea líneas de selectores de tráfico Phase 2 en formato:

    'Red_Local -> Red_Remota [Nombre_Selector]' o con alias FortiOS:
    '[Aws]*vNet-FV-UCO (172.20.10.0/24) -> [Host]*moeve (10.100.5.10/32) [to-Moeve-FV00]'
    """
    results: List[Dict[str, str]] = []
    cidr_pattern = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b")

    for line in lines:
        if not line or line.startswith("#"):
            continue

        selector_name = ""
        m_name = re.search(r"\[([^\]]+)\]\s*$", line)
        cleaned_line = line
        if m_name:
            selector_name = m_name.group(1).strip()
            cleaned_line = line[: m_name.start()].strip()

        if "->" in cleaned_line:
            parts = cleaned_line.split("->", 1)
            left = parts[0].strip()
            right = parts[1].strip()
        else:
            left = cleaned_line.strip()
            right = ""

        local_cidrs = cidr_pattern.findall(left)
        remote_cidrs = cidr_pattern.findall(right)

        results.append(
            {
                "raw": line,
                "selector_name": selector_name,
                "local_expr": left,
                "remote_expr": right,
                "local_cidr": local_cidrs[0] if local_cidrs else left,
                "remote_cidr": remote_cidrs[0] if remote_cidrs else right,
            }
        )
    return results


class B2BVPNProvisioner(Script):
    class Meta:
        name = "[VPN] Aprovisionamiento B2B VPN & NAT"
        description = (
            "Asistente universal para despliegue de túneles VPN Site-to-Site, "
            "gobernanza de NAT (SNAT/DNAT) y etiquetado cruzado."
        )
        commit_default = False

    tenant_name = StringVar(
        label="1. Proveedor / Tercero (Tenant)",
        description="Nombre de la entidad o cliente B2B. Se creará automáticamente si no existe.",
        required=True,
    )

    tunnel_name = StringVar(
        label="2. Nombre del Túnel (Opcional)",
        description=(
            "Dejar en blanco para autogenerar 'to-<proveedor>' (o con sufijos -madrid/-jesp si es Dual-Hub "
            "e incremento secuencial -01, -02... si colisiona sin adopción). Rellenar solo si se desea un nombre manual."
        ),
        required=False,
    )

    local_hub = ChoiceVar(
        choices=[
            ("madrid_cpd", "HUB 00 - Madrid CPD (1 túnel)"),
            ("jesp", "HUB 02 - JESP / Esplandiú (1 túnel)"),
            ("dual_hub", "Dual-Hub Redundante: Madrid CPD + JESP (2 túneles)"),
        ],
        label="3. Topología de Hubs Locales",
        description="Selecciona la sede central desde la que se origina la VPN o modo Dual-Hub para redundancia.",
        default="madrid_cpd",
        required=True,
    )

    adopt_existing = BooleanVar(
        label="4. Modo Adopción / Idempotente",
        description="Si el túnel ya existe en NetBox, actualizar sus atributos y comentarios en lugar de duplicar o abortar.",
        default=True,
        required=False,
    )

    peer_ip_primary = StringVar(
        label="5. IP Pública Terminador Remoto (Peer Gateway Principal)",
        description="Dirección IP pública del cortafuegos/router de la contraparte para Fase 1 IPsec.",
        required=True,
    )

    peer_ip_secondary = StringVar(
        label="6. IP Pública Terminador Remoto (Peer Gateway Secundario / Backup)",
        description="Opcional. Segunda IP pública del proveedor si dispone de contingencia Dual-Peer.",
        required=False,
    )

    crypto_profile = ChoiceVar(
        choices=[
            ("standard", "Standard B2B (IKEv2, AES-256-SHA256, DH 14)"),
            ("axpo", "Axpo Custom (IKEv2, AES-256-SHA512, DH 19)"),
            ("legacy", "Legacy B2B (IKEv2, AES-256-SHA512, DH 2)"),
            ("none", "Sin Perfil / Manual"),
        ],
        label="7. Perfil Criptográfico IPsec",
        description="Seleccionar perfil criptográfico existente en NetBox para vincular al túnel.",
        default="standard",
        required=False,
    )

    create_custom_profile = BooleanVar(
        label="8. ¿Crear nuevo perfil criptográfico en NetBox?",
        description=(
            "💡 [HINT]: Activar únicamente si el perfil criptográfico no existe previamente en NetBox. "
            "Si no está marcada, se vinculará el perfil existente seleccionado en el desplegable. "
            "Requiere especificar versión IKE, algoritmos de cifrado/integridad y Grupo DH."
        ),
        default=False,
        required=False,
    )

    custom_profile_name = StringVar(
        label="9. Nombre Nuevo Perfil IPsec (Opcional)",
        description="Nombre del nuevo perfil a crear si la casilla anterior está activa (ej. 'Partner XYZ Custom').",
        required=False,
    )

    custom_profile_ike_version = ChoiceVar(
        choices=[("2", "IKEv2"), ("1", "IKEv1")],
        label="10. Versión IKE Nuevo Perfil",
        default="2",
        required=False,
    )

    custom_profile_encryption = StringVar(
        label="11. Algoritmos Cifrado / Hash Nuevo Perfil",
        description="Algoritmos de cifrado y hash (ej. 'AES-256-SHA256').",
        default="AES-256-SHA256",
        required=False,
    )

    custom_profile_dh_group = StringVar(
        label="12. Grupo Diffie-Hellman Nuevo Perfil",
        description="Grupo DH (ej. '14', '19', '2').",
        default="14",
        required=False,
    )

    tunnel_inside_ip = StringVar(
        label="13. IP de Transferencia del Túnel (Inside IP)",
        description="Dirección IP /30 o /32 asignada a la interfaz virtual del túnel en NetBox (ej. 10.254.13.1/32).",
        required=False,
    )

    vrf_name = StringVar(
        label="14. VRF Destino IPAM",
        description="VRF en la que se registrarán las redes y traducciones NAT.",
        default="VRF-B2B-EXT",
        required=True,
    )

    tunnel_group_name = StringVar(
        label="15. Grupo de Túneles",
        description="Contenedor lógico para agrupar túneles en NetBox.",
        default="VPNs-B2B-Extranet",
        required=True,
    )

    purpose = StringVar(
        label="16. Propósito del Servicio",
        description="Descripción técnica del túnel (ej. Interconexión SCADA / Telecontrol Plantas FV).",
        required=False,
    )

    traffic_selectors = TextVar(
        label="17. Selectores Phase 2 Flexibles (1 a N / N a M)",
        description=(
            "Formato opcional avanzado por línea: 'Red_Local -> Red_Remota [Nombre_Selector]' o con alias FortiOS "
            "'172.20.10.0/24 -> 10.100.5.0/24 [to-Moeve-FV00]'. Si se especifica, anula la exigencia de cardinalidad 1:1."
        ),
        required=False,
    )

    local_prefixes = TextVar(
        label="18. Redes Locales Reales (Una por línea)",
        description="Prefijos CIDR locales anunciados hacia el túnel (ej. 172.20.10.0/24, 10.148.10.0/24).",
        required=False,
    )

    local_nat_enabled = BooleanVar(
        label="19. ¿Aplicar NAT a las Redes Locales (SNAT / 1:1)?",
        description="Marcar si las redes locales se solapan con el proveedor y deben traducirse antes de salir al túnel.",
        default=False,
        required=False,
    )

    local_nat_prefixes = TextVar(
        label="20. Redes Locales Traducidas (NAT) (Una por línea)",
        description="Prefijos CIDR resultantes en la VRF (ej. 100.97.10.0/24). Requerido si la casilla anterior está marcada.",
        required=False,
    )

    remote_prefixes = TextVar(
        label="21. Redes / IPs Remotas del Proveedor (Una por línea)",
        description="Prefijos o direcciones IP que el proveedor publica hacia nosotros a través del túnel.",
        required=False,
    )

    remote_nat_mode = ChoiceVar(
        choices=[
            ("none", "Sin NAT (Enrutamiento directo limpio)"),
            ("peer_nat", "NAT en Origen por Contraparte (Asignamos IP/Rango de nuestro pool)"),
            ("local_dnat", "DNAT Local en Firewall (Nosotros traducimos el tráfico del proveedor)"),
        ],
        label="22. Modo NAT Remoto",
        description="Estrategia de traducción para el tráfico entrante de la contraparte.",
        default="none",
        required=True,
    )

    remote_nat_targets = TextVar(
        label="23. IPs o Redes Remotas Traducidas (NAT) (Una por línea)",
        description="IPs o prefijos traducidos resultantes (ej. 100.98.200.1/32). Requerido si el modo NAT no es 'none'.",
        required=False,
    )

    # ------------------------------------------------------------------
    # Métodos de Acceso y Persistencia de Objetos
    # ------------------------------------------------------------------
    def _assign_tags(self, obj: Any, tags: List[Any], commit: bool):
        if IS_NETBOX_ENV:
            if commit and hasattr(obj, "tags") and hasattr(obj.tags, "set"):
                obj.tags.set(tags)
        else:
            obj.tags = tags

    def _get_or_create_tag(self, name: str, slug: str, color: str, description: str, commit: bool) -> Any:
        if IS_NETBOX_ENV:
            tag, created = Tag.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "color": color, "description": description},
            )
            if created and commit:
                self.log_success(f"Tag creado: {name}")
            return tag
        else:
            return Tag(name=name, slug=slug, color=color, description=description)

    def _get_or_create_tenant(self, name: str, commit: bool) -> Any:
        slug = slugify(name)
        if IS_NETBOX_ENV:
            tenant, created = Tenant.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "description": f"Proveedor / Cliente B2B: {name}"},
            )
            if created and commit:
                self.log_success(f"Tenant creado: {name}")
            return tenant
        else:
            return Tenant(name=name, slug=slug, description=f"Proveedor / Cliente B2B: {name}")

    def _get_or_create_tunnel_group(self, name: str, commit: bool) -> Any:
        if not TunnelGroup:
            return None
        slug = slugify(name)
        if IS_NETBOX_ENV:
            tg, created = TunnelGroup.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "description": "Grupo de interconexiones VPN"},
            )
            if created and commit:
                self.log_success(f"TunnelGroup creado: {name}")
            return tg
        else:
            return TunnelGroup(name=name, slug=slug, description="Grupo de interconexiones VPN")

    def _get_vrf(self, vrf_name: str) -> Optional[Any]:
        if IS_NETBOX_ENV:
            try:
                return VRF.objects.get(name=vrf_name)
            except VRF.DoesNotExist:
                return None
        return VRF(name=vrf_name)

    def _get_b2b_role(self) -> Optional[Any]:
        if IS_NETBOX_ENV:
            try:
                return Role.objects.get(slug="b2b-extranet-nat")
            except Role.DoesNotExist:
                return None
        return Role(name="B2B Extranet / NAT", slug="b2b-extranet-nat")

    def _get_or_create_prefix(
        self,
        prefix_str: str,
        vrf: Optional[Any],
        tenant: Optional[Any],
        role: Optional[Any],
        description: str,
        commit: bool,
    ) -> Any:
        """Obtiene un prefijo existente en la VRF o crea uno nuevo de forma idempotente."""
        if IS_NETBOX_ENV:
            pfx = Prefix.objects.filter(prefix=prefix_str, vrf=vrf).first()
            if pfx:
                return pfx
            pfx = Prefix(
                prefix=prefix_str,
                vrf=vrf,
                tenant=tenant,
                role=role,
                status="active",
                description=description,
            )
            if commit:
                pfx.save()
            return pfx
        else:
            return Prefix(
                prefix=prefix_str,
                vrf=vrf,
                tenant=tenant,
                role=role,
                status="active",
                description=description,
            )

    def _get_or_create_ip_address(
        self,
        address_str: str,
        vrf: Optional[Any],
        tenant: Optional[Any],
        role: Optional[Any],
        description: str,
        commit: bool,
    ) -> Any:
        """Obtiene una dirección IP existente en la VRF o crea una nueva de forma idempotente."""
        if IS_NETBOX_ENV:
            ip = IPAddress.objects.filter(address=address_str, vrf=vrf).first()
            if ip:
                return ip
            ip = IPAddress(
                address=address_str,
                vrf=vrf,
                tenant=tenant,
                role=role,
                status="active",
                description=description,
            )
            if commit:
                ip.save()
            return ip
        else:
            return IPAddress(
                address=address_str,
                vrf=vrf,
                tenant=tenant,
                role=role,
                status="active",
                description=description,
            )

    def _resolve_tunnel_names(
        self,
        manual_name: Optional[str],
        tenant_name: str,
        topology: str,
    ) -> List[Tuple[str, str]]:
        slug_tenant = slugify(tenant_name)
        base = manual_name.strip() if manual_name else f"to-{slug_tenant}"

        if topology == "dual_hub":
            if manual_name:
                t1 = f"{manual_name}-madrid"
                t2 = f"{manual_name}-jesp"
            else:
                t1 = f"to-{slug_tenant}-madrid"
                t2 = f"to-{slug_tenant}-jesp"
            return [(t1, "HUB 00 (Madrid CPD)"), (t2, "HUB 02 (JESP / Esplandiú)")]
        elif topology == "jesp":
            return [(base, "HUB 02 (JESP / Esplandiú)")]
        else:
            return [(base, "HUB 00 (Madrid CPD)")]

    def _resolve_ipsec_profile(self, data: Dict[str, Any], slug_tenant: str, commit: bool) -> Optional[Any]:
        """Resuelve o crea el perfil criptográfico IPsec según las opciones del formulario."""
        if not IPSecProfile:
            return None

        create_custom = data.get("create_custom_profile", False)
        if create_custom:
            name = (data.get("custom_profile_name") or f"Profile-{slug_tenant}").strip()
            ike_ver = int(data.get("custom_profile_ike_version", 2))
            enc = data.get("custom_profile_encryption", "AES-256-SHA256").strip()
            dh = data.get("custom_profile_dh_group", "14").strip()
            desc = f"IKEv{ike_ver} | Enc: {enc} | DH: Group {dh}"
            if IS_NETBOX_ENV:
                profile, created = IPSecProfile.objects.get_or_create(
                    name=name,
                    defaults={"description": desc, "mode": "esp", "ike_version": ike_ver},
                )
                if created and commit:
                    self.log_success(f"[IPSEC PROFILE CREADO] {name} ({desc})")
                return profile
            else:
                if commit:
                    self.log_success(f"[IPSEC PROFILE CREADO] {name} ({desc})")
                return IPSecProfile(name=name, description=desc, mode="esp", ike_version=ike_ver)
        else:
            choice = data.get("crypto_profile", "standard")
            if choice == "none":
                return None
            profile_candidates_map = {
                "standard": ["ipsec-prof-b2b-standard-dh14", "Standard B2B"],
                "axpo": ["ipsec-prof-b2b-axpo-dh19", "Axpo Custom"],
                "legacy": ["ipsec-prof-b2b-legacy-dh2", "Legacy B2B"],
            }
            candidates = profile_candidates_map.get(choice, [choice])
            if IS_NETBOX_ENV:
                profile = None
                for cand in candidates:
                    profile = IPSecProfile.objects.filter(name=cand).first()
                    if profile:
                        break
                if not profile and hasattr(IPSecProfile.objects, "filter"):
                    try:
                        profile = IPSecProfile.objects.filter(name__icontains=choice).first()
                    except Exception:
                        profile = None

                if profile:
                    self.log_info(f"[IPSEC PROFILE VINCULADO] {profile.name}")
                    return profile
                else:
                    self.log_warning(f"Perfil IPsec para '{choice}' no encontrado en NetBox ({candidates}). Se omite vinculación.")
                    return None
            else:
                return IPSecProfile(name=candidates[0])

    def _resolve_firewall_interface(self, hub_label: str, tun_name: str, commit: bool) -> Tuple[Optional[Any], Optional[Any]]:
        """Resuelve el firewall correspondiente al HUB y crea/obtiene la interfaz virtual IPsec."""
        device_name = "FortiGate-100F" if "Madrid" in hub_label else "FGT100-JES"

        if IS_NETBOX_ENV:
            device = None
            if Device:
                device = Device.objects.filter(name=device_name).first()
            iface = None
            if Interface and device:
                iface = Interface.objects.filter(device=device, name=tun_name).first()
                if not iface:
                    iface = Interface(
                        device=device,
                        name=tun_name,
                        type="virtual",
                        description=f"IPsec Virtual Interface para {tun_name}",
                        enabled=True,
                    )
                    if commit:
                        iface.save()
                        self.log_success(f"[INTERFAZ VIRTUAL CREADA] {device_name} -> {tun_name}")
            return device, iface
        else:
            dev = Device(name=device_name) if Device else None
            iface = (
                Interface(
                    device=dev,
                    name=tun_name,
                    type="virtual",
                    description=f"IPsec Virtual Interface para {tun_name}",
                    enabled=True,
                )
                if Interface
                else None
            )
            return dev, iface

    # ------------------------------------------------------------------
    # Ejecución Principal
    # ------------------------------------------------------------------
    def run(self, data: Dict[str, Any], commit: bool) -> str:
        tenant_name = data["tenant_name"].strip()
        manual_tunnel_name = data.get("tunnel_name")
        topology = data.get("local_hub", "madrid_cpd")
        adopt_existing = data.get("adopt_existing", True)
        peer_ip_pri = data["peer_ip_primary"].strip()
        peer_ip_sec = (data.get("peer_ip_secondary") or "").strip()
        vrf_name = data.get("vrf_name", "VRF-B2B-EXT").strip()
        tunnel_group_name = data.get("tunnel_group_name", "VPNs-B2B-Extranet").strip()
        purpose_desc = (data.get("purpose") or data.get("description") or "").strip()
        tunnel_inside_ip = (data.get("tunnel_inside_ip") or "").strip()

        # Parseo de Selectores Phase 2 avanzados
        raw_traffic_selectors = clean_lines(data.get("traffic_selectors"))
        parsed_selectors = parse_traffic_selectors(raw_traffic_selectors)

        local_prefixes = clean_lines(data.get("local_prefixes"))
        local_nat_enabled = data.get("local_nat_enabled", False)
        local_nat_prefixes = clean_lines(data.get("local_nat_prefixes"))

        remote_prefixes = clean_lines(data.get("remote_prefixes"))
        remote_nat_mode = data.get("remote_nat_mode", "none")
        remote_nat_targets = clean_lines(data.get("remote_nat_targets"))

        # Validaciones de cardinalidad y coherencia
        if not parsed_selectors:
            if not local_prefixes:
                raise AbortScript("Debe especificar al menos un prefijo local real.")
            if not remote_prefixes:
                raise AbortScript("Debe especificar al menos una red o IP remota del proveedor.")

            if local_nat_enabled:
                if len(local_prefixes) != len(local_nat_prefixes):
                    raise AbortScript(
                        f"Desajuste en Lado Local: {len(local_prefixes)} redes locales reales especificadas "
                        f"pero {len(local_nat_prefixes)} redes NAT introducidas. Deben tener correspondencia 1:1."
                    )

            if remote_nat_mode in ("peer_nat", "local_dnat"):
                if len(remote_prefixes) != len(remote_nat_targets):
                    raise AbortScript(
                        f"Desajuste en Lado Remoto: {len(remote_prefixes)} redes remotas especificadas "
                        f"pero {len(remote_nat_targets)} objetivos NAT introducidos. Deben tener correspondencia 1:1."
                    )
        else:
            self.log_info(f"Procesando {len(parsed_selectors)} selectores Phase 2 avanzados.")

        if not commit:
            self.log_warning("[DRY-RUN] Ejecutando en modo simulación. No se persistirán cambios en la base de datos.")
        else:
            self.log_info("[PRODUCCIÓN] Ejecutando en modo escritura transaccional.")

        # 1. Gobernanza de Tags
        slug_tenant = slugify(tenant_name)
        tunnel_tag_slug = f"vpn-{slug_tenant}"
        tunnel_tag_name = f"vpn:{slug_tenant}"
        tunnel_tag = self._get_or_create_tag(
            name=tunnel_tag_name,
            slug=tunnel_tag_slug,
            color="3b82f6",
            description=f"Túnel VPN B2B con {tenant_name}",
            commit=commit,
        )

        b2b_nat_tag = self._get_or_create_tag("B2B NAT", "b2b-nat", "f59e0b", "Tráfico B2B NAT", commit)
        b2b_remote_tag = self._get_or_create_tag("B2B Remote", "b2b-remote", "6366f1", "Objetos Remotos B2B", commit)
        overlap_tag = self._get_or_create_tag("Overlap Exception", "overlap-exception", "ef4444", "DNAT Solapamiento", commit)

        # 2. Tenancy, VRF y Roles
        tenant = self._get_or_create_tenant(tenant_name, commit=commit)
        tunnel_group = self._get_or_create_tunnel_group(tunnel_group_name, commit=commit)
        vrf = self._get_vrf(vrf_name)
        b2b_role = self._get_b2b_role()

        # 3. Procesamiento Lado Local
        assigned_local_prefixes: List[Any] = []
        provisioned_local: List[Dict[str, str]] = []
        for idx, real_pfx in enumerate(local_prefixes):
            if local_nat_enabled:
                nat_pfx = local_nat_prefixes[idx]
                desc = f"NAT 1:1 {tenant_name} | Real: {real_pfx}"
                tags = [tunnel_tag, b2b_nat_tag]
                pfx_obj = self._get_or_create_prefix(
                    prefix_str=nat_pfx,
                    vrf=vrf,
                    tenant=tenant,
                    role=b2b_role,
                    description=desc,
                    commit=commit,
                )
                self._assign_tags(pfx_obj, tags, commit)
                self.log_success(f"[LOCAL NAT] Asignado prefijo {nat_pfx} (Real: {real_pfx})")
                provisioned_local.append({"real": real_pfx, "nat": nat_pfx, "mode": "SNAT 1:1"})
                assigned_local_prefixes.append(pfx_obj)
            else:
                self.log_info(f"[LOCAL DIRECT] Prefijo real sin NAT asociado al túnel: {real_pfx}")
                provisioned_local.append({"real": real_pfx, "nat": "N/A (Directo)", "mode": "Ruta Directa"})
                if "/" in real_pfx:
                    pfx_obj = self._get_or_create_prefix(
                        prefix_str=real_pfx,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        description=f"Red Local Directa {tenant_name}",
                        commit=commit,
                    )
                    self._assign_tags(pfx_obj, [tunnel_tag], commit)
                    assigned_local_prefixes.append(pfx_obj)

        # 4. Procesamiento Lado Remoto
        assigned_remote_prefixes: List[Any] = []
        provisioned_remote: List[Dict[str, str]] = []
        for idx, rem_target in enumerate(remote_prefixes):
            if remote_nat_mode == "peer_nat":
                nat_target = remote_nat_targets[idx]
                desc = f"Host/Red NAT Remoto {tenant_name} | IP Real Proveedor: {rem_target}"
                tags = [tunnel_tag, b2b_remote_tag]
                if "/" in nat_target and nat_target.endswith("/32"):
                    ip_obj = self._get_or_create_ip_address(
                        address_str=nat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        description=desc,
                        commit=commit,
                    )
                    self._assign_tags(ip_obj, tags, commit)
                    self.log_success(f"[REMOTE NAT PEER] Reservada IP {nat_target} (Real: {rem_target})")
                else:
                    pfx_obj = self._get_or_create_prefix(
                        prefix_str=nat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        description=desc,
                        commit=commit,
                    )
                    self._assign_tags(pfx_obj, tags, commit)
                    self.log_success(f"[REMOTE NAT PEER] Reservado prefijo {nat_target} (Real: {rem_target})")
                    assigned_remote_prefixes.append(pfx_obj)
                provisioned_remote.append({"real": rem_target, "nat": nat_target, "mode": "NAT por Contraparte"})

            elif remote_nat_mode == "local_dnat":
                dnat_target = remote_nat_targets[idx]
                desc = f"DNAT Local para {tenant_name} | Remoto Original: {rem_target}"
                tags = [tunnel_tag, overlap_tag]
                if "/" in dnat_target and dnat_target.endswith("/32"):
                    ip_obj = self._get_or_create_ip_address(
                        address_str=dnat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        description=desc,
                        commit=commit,
                    )
                    self._assign_tags(ip_obj, tags, commit)
                else:
                    pfx_obj = self._get_or_create_prefix(
                        prefix_str=dnat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        description=desc,
                        commit=commit,
                    )
                    self._assign_tags(pfx_obj, tags, commit)
                    assigned_remote_prefixes.append(pfx_obj)
                self.log_success(f"[LOCAL DNAT] Mapeado DNAT {dnat_target} para {rem_target}")
                provisioned_remote.append({"real": rem_target, "nat": dnat_target, "mode": "DNAT en Firewall Local"})

            else:
                self.log_info(f"[REMOTE DIRECT] Red remota sin NAT: {rem_target}")
                provisioned_remote.append({"real": rem_target, "nat": "N/A (Directo)", "mode": "Ruta Directa"})
                if "/" in rem_target:
                    pfx_obj = self._get_or_create_prefix(
                        prefix_str=rem_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        description=f"Red Remota Directa {tenant_name}",
                        commit=commit,
                    )
                    self._assign_tags(pfx_obj, [tunnel_tag, b2b_remote_tag], commit)
                    assigned_remote_prefixes.append(pfx_obj)

        # Registrar prefijos de Phase 2 en IPAM si se especifican con formato CIDR
        cidr_pattern = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$")
        for sel in parsed_selectors:
            loc_c = sel["local_cidr"]
            rem_c = sel["remote_cidr"]
            name_sel = sel["selector_name"] or "Phase 2"
            if cidr_pattern.match(loc_c):
                pfx_obj = self._get_or_create_prefix(
                    prefix_str=loc_c,
                    vrf=vrf,
                    tenant=tenant,
                    role=b2b_role,
                    description=f"Phase 2 Local [{name_sel}] | {sel['local_expr']}",
                    commit=commit,
                )
                self._assign_tags(pfx_obj, [tunnel_tag], commit)
                assigned_local_prefixes.append(pfx_obj)
            if cidr_pattern.match(rem_c):
                pfx_obj = self._get_or_create_prefix(
                    prefix_str=rem_c,
                    vrf=vrf,
                    tenant=tenant,
                    role=b2b_role,
                    description=f"Phase 2 Remoto [{name_sel}] | {sel['remote_expr']}",
                    commit=commit,
                )
                self._assign_tags(pfx_obj, [tunnel_tag, b2b_remote_tag], commit)
                assigned_remote_prefixes.append(pfx_obj)

        # 5. Modelado de Perfil Criptográfico
        ipsec_profile = self._resolve_ipsec_profile(data, slug_tenant, commit)

        # 6. Modelado de Túnel(es) VPN y Terminaciones
        tunnel_configs = self._resolve_tunnel_names(manual_tunnel_name, tenant_name, topology)

        # Preparar comentarios Markdown estructurados
        markdown_comments = [
            f"## Interconexión VPN B2B: {tenant_name}",
            f"- **Propósito**: {purpose_desc or 'Conectividad B2B Site-to-Site'}",
            f"- **Peer Gateway Principal**: `{peer_ip_pri}`",
            f"- **Peer Gateway Secundario**: `{peer_ip_sec or 'N/A'}`",
            f"- **VRF**: `{vrf_name}`",
            f"- **Tag Global**: `{tunnel_tag_name}`",
            f"- **Perfil IPsec**: `{getattr(ipsec_profile, 'name', 'N/A')}`",
        ]
        if tunnel_inside_ip:
            markdown_comments.append(f"- **Inside IP / Transferencia**: `{tunnel_inside_ip}`")

        if parsed_selectors:
            markdown_comments.extend([
                "",
                "### Selectores Phase 2 (Matriz de Tráfico)",
                "| Selector / Nombre | Red Local / Alias | Red Remota / Alias |",
                "| :--- | :--- | :--- |",
            ])
            for s in parsed_selectors:
                s_name = s["selector_name"] or "P2"
                markdown_comments.append(f"| `{s_name}` | `{s['local_expr']}` | `{s['remote_expr']}` |")

        if provisioned_local:
            markdown_comments.extend([
                "",
                "### Matriz de Tráfico y NAT Local",
                "| Red Real Local | Red Publicada (NAT) | Tipo de Enrutamiento |",
                "| :--- | :--- | :--- |",
            ])
            for item in provisioned_local:
                markdown_comments.append(f"| `{item['real']}` | `{item['nat']}` | {item['mode']} |")

        if provisioned_remote:
            markdown_comments.extend([
                "",
                "### Matriz de Tráfico y NAT Remoto",
                "| Red/IP Real Remota | Red/IP en Edison (NAT) | Tipo de Enrutamiento |",
                "| :--- | :--- | :--- |",
            ])
            for item in provisioned_remote:
                markdown_comments.append(f"| `{item['real']}` | `{item['nat']}` | {item['mode']} |")

        comments_payload = "\n".join(markdown_comments)

        created_tunnels: List[str] = []
        if Tunnel:
            for tun_name, hub_label in tunnel_configs:
                # Resolver interfaz virtual en el firewall del HUB
                dev_obj, iface_obj = self._resolve_firewall_interface(hub_label, tun_name, commit)

                # Registrar Inside IP si se especifica
                if tunnel_inside_ip and iface_obj:
                    inside_ip_obj = IPAddress(
                        address=tunnel_inside_ip,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        status="active",
                        description=f"Inside IP túnel {tun_name}",
                        assigned_object=iface_obj,
                    )
                    if commit:
                        inside_ip_obj.save()
                    self._assign_tags(inside_ip_obj, [tunnel_tag], commit)
                    self.log_success(
                        f"[INSIDE IP] Asignada IP {tunnel_inside_ip} a interfaz {tun_name} ({getattr(dev_obj, 'name', '')})"
                    )

                # Extraer PKs de los prefijos asignados para Custom Fields multiobject
                local_pks = [getattr(p, "pk", getattr(p, "id", None)) for p in assigned_local_prefixes]
                local_pks = [pk for pk in dict.fromkeys(local_pks) if pk is not None]

                remote_pks = [getattr(p, "pk", getattr(p, "id", None)) for p in assigned_remote_prefixes]
                remote_pks = [pk for pk in dict.fromkeys(remote_pks) if pk is not None]

                # Modo Adopción o Creación Idempotente
                tun_obj = None
                if adopt_existing:
                    if IS_NETBOX_ENV:
                        tun_obj = Tunnel.objects.filter(name=tun_name).first()
                    # Si ya existe en NetBox, actualizar
                    if tun_obj:
                        tun_obj.status = "active"
                        tun_obj.encapsulation = "ipsec-tunnel"
                        tun_obj.tunnel_group = tunnel_group
                        tun_obj.tenant = tenant
                        tun_obj.ipsec_profile = ipsec_profile
                        tun_obj.description = f"VPN B2B {tenant_name} desde {hub_label}"
                        tun_obj.comments = comments_payload
                        if not hasattr(tun_obj, "custom_field_data") or tun_obj.custom_field_data is None:
                            tun_obj.custom_field_data = {}
                        tun_obj.custom_field_data["local_prefixes"] = local_pks
                        tun_obj.custom_field_data["remote_prefixes"] = remote_pks
                        if commit:
                            tun_obj.save()
                        self.log_info(f"[ADOPTADO] Túnel existente actualizado sin duplicar: {tun_name}")

                if not tun_obj:
                    tun_obj = Tunnel(
                        name=tun_name,
                        status="active",
                        encapsulation="ipsec-tunnel",
                        tunnel_group=tunnel_group,
                        tenant=tenant,
                        ipsec_profile=ipsec_profile,
                        description=f"VPN B2B {tenant_name} desde {hub_label}",
                        comments=comments_payload,
                        custom_field_data={
                            "local_prefixes": local_pks,
                            "remote_prefixes": remote_pks,
                        },
                    )
                    if not hasattr(tun_obj, "custom_field_data") or tun_obj.custom_field_data is None:
                        tun_obj.custom_field_data = {}
                    tun_obj.custom_field_data["local_prefixes"] = local_pks
                    tun_obj.custom_field_data["remote_prefixes"] = remote_pks
                    if commit:
                        tun_obj.save()
                    self.log_success(f"[TÚNEL CREADO] {tun_name} ({hub_label}) -> Peer: {peer_ip_pri}")

                self._assign_tags(tun_obj, [tunnel_tag], commit)
                created_tunnels.append(tun_name)

                # Registrar terminaciones (Local vinculada a dcim.interface y Remota con outside_ip)
                if TunnelTermination:
                    # Terminación local
                    try:
                        ct_iface = None
                        if ContentType:
                            if IS_NETBOX_ENV:
                                ct_iface = ContentType.objects.get(app_label="dcim", model="interface")
                            else:
                                ct_iface = ContentType.objects.get("dcim", "interface")

                        term_local = TunnelTermination(
                            tunnel=tun_obj,
                            role="hub" if topology == "dual_hub" else "peer",
                            termination_type=ct_iface or "dcim.interface",
                            termination_id=getattr(iface_obj, "id", 1) if iface_obj else None,
                            termination=iface_obj,
                        )
                        if commit:
                            term_local.save()
                    except Exception as e:
                        self.log_warning(f"No se pudo registrar TunnelTermination local para {tun_name}: {e}")

                    # Terminación remota
                    try:
                        term_remote = TunnelTermination(
                            tunnel=tun_obj,
                            role="peer",
                            outside_ip=peer_ip_pri,
                        )
                        if commit:
                            term_remote.save()
                    except Exception as e:
                        self.log_warning(f"No se pudo registrar TunnelTermination remota para {tun_name}: {e}")

        summary_msg = (
            f"Aprovisionamiento completado con éxito para {tenant_name}. "
            f"Túneles gestionados: {', '.join(created_tunnels)}. "
            f"Tag dinámico asignado: {tunnel_tag_name}. "
            f"Perfil IPsec: {getattr(ipsec_profile, 'name', 'N/A')}. "
            f"Selectores procesados: {len(parsed_selectors) if parsed_selectors else len(local_prefixes)}."
        )
        self.log_info(summary_msg)
        return summary_msg
