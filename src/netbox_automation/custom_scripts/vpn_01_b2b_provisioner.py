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
    try:
        from vpn.models import Tunnel, TunnelGroup, TunnelTermination
    except ImportError:
        Tunnel = None
        TunnelGroup = None
        TunnelTermination = None
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
        Tunnel,
        TunnelGroup,
        TunnelTermination,
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
            "e incremento secuencial -01, -02... si colisiona). Rellenar solo si se desea un nombre manual."
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

    peer_ip_primary = StringVar(
        label="4. IP Pública Terminador Remoto (Peer Gateway Principal)",
        description="Dirección IP pública del cortafuegos/router de la contraparte para Fase 1 IPsec.",
        required=True,
    )

    peer_ip_secondary = StringVar(
        label="5. IP Pública Terminador Remoto (Peer Gateway Secundario / Backup)",
        description="Opcional. Segunda IP pública del proveedor si dispone de contingencia Dual-Peer.",
        required=False,
    )

    vrf_name = StringVar(
        label="6. VRF Destino IPAM",
        description="VRF en la que se registrarán las redes y traducciones NAT.",
        default="VRF-B2B-EXT",
        required=True,
    )

    tunnel_group_name = StringVar(
        label="7. Grupo de Túneles",
        description="Contenedor lógico para agrupar túneles en NetBox.",
        default="VPNs-B2B-Extranet",
        required=True,
    )

    purpose = StringVar(
        label="8. Propósito del Servicio",
        description="Descripción técnica del túnel (ej. Interconexión SCADA / Telecontrol Plantas FV).",
        required=False,
    )

    local_prefixes = TextVar(
        label="9. Redes Locales Reales (Una por línea)",
        description="Prefijos CIDR locales anunciados hacia el túnel (ej. 172.20.10.0/24, 10.148.10.0/24).",
        required=True,
    )

    local_nat_enabled = BooleanVar(
        label="10. ¿Aplicar NAT a las Redes Locales (SNAT / 1:1)?",
        description="Marcar si las redes locales se solapan con el proveedor y deben traducirse antes de salir al túnel.",
        default=False,
        required=False,
    )

    local_nat_prefixes = TextVar(
        label="11. Redes Locales Traducidas (NAT) (Una por línea)",
        description="Prefijos CIDR resultantes en la VRF (ej. 100.97.10.0/24). Requerido si la casilla anterior está marcada.",
        required=False,
    )

    remote_prefixes = TextVar(
        label="12. Redes / IPs Remotas del Proveedor (Una por línea)",
        description="Prefijos o direcciones IP que el proveedor publica hacia nosotros a través del túnel.",
        required=True,
    )

    remote_nat_mode = ChoiceVar(
        choices=[
            ("none", "Sin NAT (Enrutamiento directo limpio)"),
            ("peer_nat", "NAT en Origen por Contraparte (Asignamos IP/Rango de nuestro pool)"),
            ("local_dnat", "DNAT Local en Firewall (Nosotros traducimos el tráfico del proveedor)"),
        ],
        label="13. Modo NAT Remoto",
        description="Estrategia de traducción para el tráfico entrante de la contraparte.",
        default="none",
        required=True,
    )

    remote_nat_targets = TextVar(
        label="14. IPs o Redes Remotas Traducidas (NAT) (Una por línea)",
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

    # ------------------------------------------------------------------
    # Ejecución Principal
    # ------------------------------------------------------------------
    def run(self, data: Dict[str, Any], commit: bool) -> str:
        tenant_name = data["tenant_name"].strip()
        manual_tunnel_name = data.get("tunnel_name")
        topology = data.get("local_hub", "madrid_cpd")
        peer_ip_pri = data["peer_ip_primary"].strip()
        peer_ip_sec = (data.get("peer_ip_secondary") or "").strip()
        vrf_name = data.get("vrf_name", "VRF-B2B-EXT").strip()
        tunnel_group_name = data.get("tunnel_group_name", "VPNs-B2B-Extranet").strip()
        purpose_desc = (data.get("purpose") or data.get("description") or "").strip()

        local_prefixes = clean_lines(data.get("local_prefixes"))
        local_nat_enabled = data.get("local_nat_enabled", False)
        local_nat_prefixes = clean_lines(data.get("local_nat_prefixes"))

        remote_prefixes = clean_lines(data.get("remote_prefixes"))
        remote_nat_mode = data.get("remote_nat_mode", "none")
        remote_nat_targets = clean_lines(data.get("remote_nat_targets"))

        # Validaciones de cardinalidad y coherencia
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
        provisioned_local: List[Dict[str, str]] = []
        for idx, real_pfx in enumerate(local_prefixes):
            if local_nat_enabled:
                nat_pfx = local_nat_prefixes[idx]
                desc = f"NAT 1:1 {tenant_name} | Real: {real_pfx}"
                tags = [tunnel_tag, b2b_nat_tag]
                pfx_obj = Prefix(
                    prefix=nat_pfx,
                    vrf=vrf,
                    tenant=tenant,
                    role=b2b_role,
                    status="active",
                    description=desc,
                )
                if commit:
                    pfx_obj.save()
                self._assign_tags(pfx_obj, tags, commit)
                self.log_success(f"[LOCAL NAT] Asignado prefijo {nat_pfx} (Real: {real_pfx})")
                provisioned_local.append({"real": real_pfx, "nat": nat_pfx, "mode": "SNAT 1:1"})
            else:
                self.log_info(f"[LOCAL DIRECT] Prefijo real sin NAT asociado al túnel: {real_pfx}")
                provisioned_local.append({"real": real_pfx, "nat": "N/A (Directo)", "mode": "Ruta Directa"})

        # 4. Procesamiento Lado Remoto
        provisioned_remote: List[Dict[str, str]] = []
        for idx, rem_target in enumerate(remote_prefixes):
            if remote_nat_mode == "peer_nat":
                nat_target = remote_nat_targets[idx]
                desc = f"Host/Red NAT Remoto {tenant_name} | IP Real Proveedor: {rem_target}"
                tags = [tunnel_tag, b2b_remote_tag]
                if "/" in nat_target and nat_target.endswith("/32"):
                    ip_obj = IPAddress(
                        address=nat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        status="active",
                        description=desc,
                    )
                    if commit:
                        ip_obj.save()
                    self._assign_tags(ip_obj, tags, commit)
                    self.log_success(f"[REMOTE NAT PEER] Reservada IP {nat_target} (Real: {rem_target})")
                else:
                    pfx_obj = Prefix(
                        prefix=nat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        status="active",
                        description=desc,
                    )
                    if commit:
                        pfx_obj.save()
                    self._assign_tags(pfx_obj, tags, commit)
                    self.log_success(f"[REMOTE NAT PEER] Reservado prefijo {nat_target} (Real: {rem_target})")
                provisioned_remote.append({"real": rem_target, "nat": nat_target, "mode": "NAT por Contraparte"})

            elif remote_nat_mode == "local_dnat":
                dnat_target = remote_nat_targets[idx]
                desc = f"DNAT Local para {tenant_name} | Remoto Original: {rem_target}"
                tags = [tunnel_tag, overlap_tag]
                if "/" in dnat_target and dnat_target.endswith("/32"):
                    ip_obj = IPAddress(
                        address=dnat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        status="active",
                        description=desc,
                    )
                    if commit:
                        ip_obj.save()
                    self._assign_tags(ip_obj, tags, commit)
                else:
                    pfx_obj = Prefix(
                        prefix=dnat_target,
                        vrf=vrf,
                        tenant=tenant,
                        role=b2b_role,
                        status="active",
                        description=desc,
                    )
                    if commit:
                        pfx_obj.save()
                    self._assign_tags(pfx_obj, tags, commit)
                self.log_success(f"[LOCAL DNAT] Mapeado DNAT {dnat_target} para {rem_target}")
                provisioned_remote.append({"real": rem_target, "nat": dnat_target, "mode": "DNAT en Firewall Local"})

            else:
                self.log_info(f"[REMOTE DIRECT] Red remota sin NAT: {rem_target}")
                provisioned_remote.append({"real": rem_target, "nat": "N/A (Directo)", "mode": "Ruta Directa"})

        # 5. Modelado de Túnel(es) VPN y Terminaciones
        tunnel_configs = self._resolve_tunnel_names(manual_tunnel_name, tenant_name, topology)

        # Preparar tabla Markdown para comentarios del túnel
        markdown_comments = [
            f"## Interconexión VPN B2B: {tenant_name}",
            f"- **Propósito**: {purpose_desc or 'Conectividad B2B Site-to-Site'}",
            f"- **Peer Gateway Principal**: `{peer_ip_pri}`",
            f"- **Peer Gateway Secundario**: `{peer_ip_sec or 'N/A'}`",
            f"- **VRF**: `{vrf_name}`",
            f"- **Tag Global**: `{tunnel_tag_name}`",
            "",
            "### Matriz de Tráfico y NAT Local",
            "| Red Real Local | Red Publicada (NAT) | Tipo de Enrutamiento |",
            "| :--- | :--- | :--- |",
        ]
        for item in provisioned_local:
            markdown_comments.append(f"| `{item['real']}` | `{item['nat']}` | {item['mode']} |")

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
                tun_obj = Tunnel(
                    name=tun_name,
                    status="active",
                    encapsulation="ipsec-tunnel",
                    tunnel_group=tunnel_group,
                    tenant=tenant,
                    description=f"VPN B2B {tenant_name} desde {hub_label}",
                    comments=comments_payload,
                )
                if commit:
                    tun_obj.save()
                self._assign_tags(tun_obj, [tunnel_tag], commit)

                if TunnelTermination:
                    try:
                        term_obj = TunnelTermination(
                            tunnel=tun_obj,
                            role="peer",
                        )
                        if commit:
                            term_obj.save()
                    except Exception as e:
                        self.log_warning(f"No se pudo registrar TunnelTermination para {tun_name}: {e}")

                self.log_success(f"[TÚNEL CREADO] {tun_name} ({hub_label}) -> Peer: {peer_ip_pri}")
                created_tunnels.append(tun_name)

        summary_msg = (
            f"Aprovisionamiento completado con éxito para {tenant_name}. "
            f"Túneles gestionados: {', '.join(created_tunnels)}. "
            f"Tag dinámico asignado: {tunnel_tag_name}. "
            f"Redes locales procesadas: {len(local_prefixes)}. "
            f"Redes remotas procesadas: {len(remote_prefixes)}."
        )
        self.log_info(summary_msg)
        return summary_msg
