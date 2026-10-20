"""Definiciones de datos y catálogo de red/IPAM para ingesta en NetBox (Fase 2)."""

from typing import Any, Dict, List

# 1. Catálogo de Roles IPAM
IPAM_ROLES: List[Dict[str, Any]] = [
    {"name": "Supernet Container", "slug": "supernet-container", "color": "4a5568", "description": "Bloque agregador o contenedor de direccionamiento"},
    {"name": "Corporate LAN (Cable)", "slug": "lan-datos-cable", "color": "0284c7", "description": "Red de datos cableada para puestos de trabajo"},
    {"name": "Corporate Wi-Fi", "slug": "lan-wifi-corp", "color": "06b6d4", "description": "Red inalámbrica corporativa 802.1X"},
    {"name": "Voice over IP (VoIP)", "slug": "lan-voz-ip", "color": "8b5cf6", "description": "Telefonía IP, terminales SIP y videoconferencia"},
    {"name": "Printers", "slug": "lan-impresoras", "color": "64748b", "description": "Impresoras y multifuncionales de red"},
    {"name": "Servers / DC", "slug": "lan-servidores", "color": "10b981", "description": "Servidores locales, hipervisores y almacenamiento"},
    {"name": "OT / Industrial", "slug": "lan-ot-industrial", "color": "f59e0b", "description": "Red industrial, SCADA, PLCs y telecontrol"},
    {"name": "Guest Network (DIA)", "slug": "lan-invitados", "color": "ec4899", "description": "Acceso a Internet directo para visitas"},
    {"name": "CCTV & Physical Security", "slug": "lan-cctv-seguridad", "color": "ef4444", "description": "Cámaras IP, NVRs y control de accesos"},
    {"name": "Cloud Transit / SD-WAN", "slug": "cloud-transit-sdwan", "color": "3b82f6", "description": "Hubs de conectividad y tránsito Cloud (TGW / SD-WAN)"},
    {"name": "Cloud Workload", "slug": "cloud-workload", "color": "14b8a6", "description": "Cargas de trabajo y VPCs productivas en nube"},
    {"name": "VPN Dial-up Pool", "slug": "vpn-dialup-pool", "color": "6366f1", "description": "Pools dinámicos para clientes VPN remotos"},
    {"name": "B2B Extranet / NAT", "slug": "b2b-extranet-nat", "color": "d97706", "description": "Rangos de traducción NAT y extranet de terceros"},
    {"name": "BGP Peering APIPA", "slug": "bgp-peering-apipa", "color": "84cc16", "description": "Enlaces punto a punto BGP sobre APIPA (169.254.x.x)"},
    {"name": "Inter-Hub Transit", "slug": "inter-hub-transit", "color": "0ea5e9", "description": "Interconexión troncal entre centros de datos (Hubs)"},
    {"name": "Fotovoltaica / Solar", "slug": "fotovoltaica-solar", "color": "eab308", "description": "Redes de generación fotovoltaica y plantas solares"},
    {"name": "Legacy / Flat Network", "slug": "legacy-flat-network", "color": "94a3b8", "description": "Redes heredadas no migradas o sin segmentación"},
    {"name": "Management / Infrastructure (MGMT)", "slug": "lan-gestion-infra", "color": "0f766e", "description": "Red de gestión interna de firewalls, switches y electrónica de red"},
    {"name": "Restricted Network (RSTD)", "slug": "lan-restringida-rstd", "color": "8b5cf6", "description": "Red de comunicaciones restringidas, VoIP y tráfico segregado"},
]

# 2. VRFs
VRFS: List[Dict[str, Any]] = [
    {
        "name": "VRF-B2B-EXT",
        "rd": "64000:6598",
        "description": "Tabla de enrutamiento dedicada para interconexiones B2B, solapamientos y CGNAT RFC 6598",
    }
]

# 2.1 RIRs (Regional Internet Registries)
RIRS: List[Dict[str, Any]] = [
    {
        "name": "RIPE NCC",
        "slug": "ripe-ncc",
        "is_private": False,
        "description": "Registro Regional de Internet para Europa, Oriente Medio y Asia Central",
    },
    {
        "name": "RFC 6996 (Private ASNs)",
        "slug": "rfc-6996",
        "is_private": True,
        "description": "Rango de números de sistema autónomo privados (64512-65534)",
    },
    {
        "name": "RFC 1918 (Private IP Space)",
        "slug": "rfc-1918",
        "is_private": True,
        "description": "Espacio de direccionamiento IPv4 privado (10/8, 172.16/12, 192.168/16)",
    },
    {
        "name": "RFC 6598 (CGNAT Space)",
        "slug": "rfc-6598",
        "is_private": True,
        "description": "Espacio de direcciones compartidas para CGNAT (100.64.0.0/10)",
    },
]

# 2.2 ASNs (Autonomous System Numbers)
ASNS: List[Dict[str, Any]] = [
    {
        "asn": 64000,
        "rir_slug": "rfc-6996",
        "description": "Edison Global Corporate / iBGP Hubs & Spokes",
    },
    {
        "asn": 64512,
        "rir_slug": "rfc-6996",
        "description": "AWS Cloud Transit Gateway (eu-west-1)",
    },
    {
        "asn": 65515,
        "rir_slug": "rfc-6996",
        "description": "Azure Virtual Network Gateway (West Europe)",
    },
    {
        "asn": 65003,
        "rir_slug": "rfc-6996",
        "site_slug": "madrid-cpd",
        "description": "Madrid CPD - Inter-Hub eBGP Peering (HUB 00)",
    },
    {
        "asn": 65004,
        "rir_slug": "rfc-6996",
        "site_slug": "jesp",
        "description": "JESP - Inter-Hub eBGP Peering (HUB 02)",
    },
]

# 3. Plantilla estándar real de VLANs (extraída de firewalls en producción)
STANDARD_VLANS: List[Dict[str, Any]] = [
    {
        "vid": 10,
        "name": "LAN_Datos_Cable",
        "role_slug": "lan-datos-cable",
        "third_octet": 10,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Puestos de trabajo físicos cableados (802.1X)",
    },
    {
        "vid": 11,
        "name": "LAN_WiFi_Corp",
        "role_slug": "lan-wifi-corp",
        "third_octet": 11,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Portátiles y móviles corporativos (SSID EDISON_NEXT)",
    },
    {
        "vid": 20,
        "name": "LAN_Invitados",
        "role_slug": "lan-invitados",
        "third_octet": 12,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Wi-Fi de visitas (SSID INVITADOS_EDISON_NEXT) con salida directa DIA",
    },
    {
        "vid": 30,
        "name": "LAN_Impresoras",
        "role_slug": "lan-impresoras",
        "third_octet": 13,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Impresoras de red multifunción y servidores de impresión",
    },
    {
        "vid": 40,
        "name": "LAN_CCTV_Seguridad",
        "role_slug": "lan-cctv-seguridad",
        "third_octet": 14,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Cámaras de videovigilancia IP, NVRs y control de accesos",
    },
    {
        "vid": 50,
        "name": "LAN_Restringida_RSTD",
        "role_slug": "lan-restringida-rstd",
        "third_octet": 15,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Red de comunicaciones restringidas, VoIP y tráfico segregado",
    },
    {
        "vid": 60,
        "name": "LAN_OT_Industrial",
        "role_slug": "lan-ot-industrial",
        "third_octet": 16,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Autómatas industriales, PLCs, telecontrol y SCADA",
    },
    {
        "vid": 80,
        "name": "LAN_Gestion_Infra",
        "role_slug": "lan-gestion-infra",
        "third_octet": 17,
        "mask": "/25",
        "gateway_offset": 126,
        "description": "Gestión interna de firewalls, switches y electrónica (GW .126 /25)",
    },
    {
        "vid": 90,
        "name": "LAN_Servidores",
        "role_slug": "lan-servidores",
        "third_octet": 18,
        "mask": "/24",
        "gateway_offset": 254,
        "description": "Servidores locales de sucursal, NAS y controladores",
    },
]

# 4. Sedes Hubs (Datacenters)
HUB_SITES: List[Dict[str, Any]] = [
    {
        "name": "Madrid CPD",
        "slug": "madrid-cpd",
        "second_octet": 148,
        "description": "Centro de Datos Primario (HUB 00 - Madrid Core)",
        "group_name": "Oficinas Corporativas",
    },
    {
        "name": "JESP",
        "slug": "jesp",
        "second_octet": 152,
        "description": "Centro de Datos Secundario (HUB 02 - JES Core 2)",
        "group_name": "Oficinas Corporativas",
    },
]

# 5. Mapeo de Sedes Spokes a segundo octeto (10.XX.0.0/16)
SPOKE_SITES: List[Dict[str, Any]] = [
    {"site_name": "Delegación Barcelona - Zona Franca", "site_slug": "delegacion-barcelona-zona-franca", "second_octet": 151, "alias": "ZNF"},
    {"site_name": "Delegación Palma De Mallorca", "site_slug": "delegacion-palma-de-mallorca", "second_octet": 153, "alias": "PDM"},
    {"site_name": "Delegación Sevilla", "site_slug": "delegacion-sevilla", "second_octet": 154, "alias": "SEV"},
    {"site_name": "PackBenefit", "site_slug": "packbenefit", "second_octet": 156, "alias": "PBF"},
    {"site_name": "Delegación Alcalá De Henares", "site_slug": "delegacion-alcala-de-henares", "second_octet": 157, "alias": "ADH"},
    {"site_name": "ILAS Reny Picot", "site_slug": "ilas-reny-picot", "second_octet": 158, "alias": "ILAS"},
    {"site_name": "EL POZO", "site_slug": "el-pozo", "second_octet": 159, "alias": "EPZ"},
    {"site_name": "Delegación Ibiza", "site_slug": "delegacion-ibiza", "second_octet": 160, "alias": "IBZ"},
    {"site_name": "Delegación Molins De Rei", "site_slug": "delegacion-molins-de-rei", "second_octet": 161, "alias": "MDR"},
    {"site_name": "Delegación Sant Boi De Llobregat", "site_slug": "delegacion-sant-boi-de-llobregat", "second_octet": 163, "alias": "SBL"},
    {"site_name": "Delegación Sant Cugat Del Vallès", "site_slug": "delegacion-sant-cugat-del-valles", "second_octet": 164, "alias": "SCV"},
    {"site_name": "Oficina Gijón", "site_slug": "oficina-gijon", "second_octet": 165, "alias": "GIJ-OFI"},
    {"site_name": "IVECO Madrid", "site_slug": "iveco-madrid", "second_octet": 166, "alias": "IVECO-MAD"},
    {"site_name": "ArcelorMittal Avilés", "site_slug": "arcelormittal-aviles", "second_octet": 168, "alias": "ARC-AVI"},
    {"site_name": "ArcelorMittal Veriña", "site_slug": "arcelormittal-verina", "second_octet": 169, "alias": "ARC-GIJ"},
    {"site_name": "COREN CAT", "site_slug": "coren-cat", "second_octet": 170, "alias": "COR-SCI"},
    {"site_name": "COREN ROLLS", "site_slug": "coren-rolls", "second_octet": 171, "alias": "COR-ARR"},
    {"site_name": "DAMM", "site_slug": "damm", "second_octet": 172, "alias": "DAMM"},
    {"site_name": "EAMSA", "site_slug": "eamsa", "second_octet": 173, "alias": "EAMSA"},
    {"site_name": "Fompedraza", "site_slug": "fompedraza", "second_octet": 174, "alias": "FOM"},
    {"site_name": "IVECO Valladolid", "site_slug": "iveco-valladolid", "second_octet": 175, "alias": "IVECO-VALL"},
    {"site_name": "INLEIT", "site_slug": "inleit", "second_octet": 176, "alias": "INLEIT"},
    {"site_name": "Guijuelo Fonz", "site_slug": "guijuelo-fonz", "second_octet": 177, "alias": "FONZ"},
    {"site_name": "Guijuelo Monzón", "site_slug": "guijuelo-monzon", "second_octet": 178, "alias": "MONZON"},
    {"site_name": "Guijuelo San Millan", "site_slug": "guijuelo-san-millan", "second_octet": 179, "alias": "SANMILLAN"},
    {"site_name": "Guijuelo Milagros", "site_slug": "guijuelo-milagros", "second_octet": 180, "alias": "MILAGROS"},
    {"site_name": "Leche Celta Pontedeume", "site_slug": "leche-celta-pontedeume", "second_octet": 181, "alias": "LCP"},
    {"site_name": "Leche Celta Meruelo", "site_slug": "leche-celta-meruelo", "second_octet": 182, "alias": "LCM"},
    {"site_name": "Leche Celta Ávila", "site_slug": "leche-celta-avila", "second_octet": 183, "alias": "LCA"},
    {"site_name": "TEST-JESP", "site_slug": "test-jesp", "second_octet": 191, "alias": "TEST-JESP"},
]

# 6. Prefijos Globales y Contenedores
GLOBAL_CONTAINER_PREFIXES: List[Dict[str, Any]] = [
    {
        "prefix": "10.144.0.0/12",
        "status": "container",
        "role_slug": "supernet-container",
        "description": "Bloque 1: Espacio corporativo para Hubs, Sedes y Servicios (10.144.0.0/16 - 10.159.0.0/16)",
    },
    {
        "prefix": "10.160.0.0/10",
        "status": "container",
        "role_slug": "supernet-container",
        "description": "Bloque 2: Espacio asignado y disponible para despliegue y crecimiento de sedes remotas",
    },
    {
        "prefix": "172.20.0.0/16",
        "status": "container",
        "role_slug": "fotovoltaica-solar",
        "description": "Red corporativa de plantas solares y generación fotovoltaica",
    },
    {
        "prefix": "100.64.0.0/10",
        "status": "container",
        "role_slug": "b2b-extranet-nat",
        "vrf_name": "VRF-B2B-EXT",
        "description": "Espacio CGNAT RFC 6598 reservado para traducciones DNAT/SNAT con terceros",
    },
]

# 7. Prefijos Cloud Multi-Cloud (AWS y Azure)
CLOUD_PREFIXES: List[Dict[str, Any]] = [
    # AWS
    {
        "prefix": "10.100.0.0/16",
        "status": "active",
        "role_slug": "cloud-transit-sdwan",
        "description": "AWS: edx-networking (ind-sdwan-vpc) - Hub central de conectividad y tránsito TGW",
    },
    {
        "prefix": "10.102.0.0/16",
        "status": "reserved",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-backup - Espacio reservado para cuenta de backup",
    },
    {
        "prefix": "10.105.0.0/16",
        "status": "container",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-infra-tools - Espacio de cuenta de herramientas compartidas",
    },
    {
        "prefix": "10.105.0.0/22",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-infra-tools-vpc - Herramientas y servicios compartidos",
    },
    {
        "prefix": "10.110.0.0/16",
        "status": "container",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-delivery-prod - Espacio WLS de delivery",
    },
    {
        "prefix": "10.110.0.0/22",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-delivery-prod-01-vpc - Entorno productivo Delivery",
    },
    {
        "prefix": "10.111.0.0/16",
        "status": "container",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-general-services-prod - Espacio WLS servicios generales",
    },
    {
        "prefix": "10.111.0.0/22",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-general-services-prod-01-vpc - Servicios generales de producción",
    },
    {
        "prefix": "10.112.0.0/16",
        "status": "container",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-bcare-prod - Espacio WLS BCare",
    },
    {
        "prefix": "10.112.0.0/22",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "AWS: edx-bcare-prod-01-vpc - Entorno productivo BCare",
    },
    {
        "prefix": "10.128.0.0/16",
        "status": "container",
        "role_slug": "cloud-workload",
        "description": "AWS: obras-prod - Espacio WLS Obras",
    },
    {
        "prefix": "10.128.0.0/22",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "AWS: sis-obras-prod-01-vpc - Entorno productivo de Obras e ingeniería",
    },
    {
        "prefix": "172.31.0.0/16",
        "status": "active",
        "role_slug": "legacy-flat-network",
        "description": "AWS: edx-former-workloads (VPCDefault) - Cargas históricas / NAT terceros",
    },
    {
        "prefix": "172.48.0.0/16",
        "status": "active",
        "role_slug": "legacy-flat-network",
        "description": "AWS: bcare-prod-vpc (Legacy BCare)",
    },
    # Azure
    {
        "prefix": "10.0.0.0/16",
        "status": "container",
        "role_slug": "cloud-workload",
        "description": "Azure: edf-shared-rg-vnet / vnet-rzcitzch (West Europe)",
    },
    {
        "prefix": "10.1.0.0/16",
        "status": "container",
        "role_slug": "cloud-workload",
        "description": "Azure: edison-build2 / edison-dev VNets (West Europe)",
    },
    {
        "prefix": "10.10.0.0/16",
        "status": "active",
        "role_slug": "cloud-transit-sdwan",
        "description": "Azure: edf-hub-vnet - Hub de conectividad Azure (West Europe)",
    },
    {
        "prefix": "10.11.0.0/24",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "Azure: pub-ax-prod-main-vnet (West Europe)",
    },
    {
        "prefix": "10.20.1.0/24",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "Azure: glo-informesdyn365pbi-dev-vnet (West Europe)",
    },
    {
        "prefix": "10.20.2.0/24",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "Azure: glo-justdrive-shared-vnet (West Europe)",
    },
    {
        "prefix": "10.30.0.0/24",
        "status": "active",
        "role_slug": "cloud-workload",
        "description": "Azure: glo-pds-siem-main-vnet (West Europe)",
    },
]

# 8. Prefijos de Tránsito Troncal, Overlays, BGP APIPA y VPN Pools
INFRA_TRANSIT_PREFIXES: List[Dict[str, Any]] = [
    # Overlays Hub-Spoke
    {
        "prefix": "10.254.10.0/24",
        "status": "active",
        "role_slug": "cloud-transit-sdwan",
        "site_slug": "madrid-cpd",
        "description": "Overlay HubVPN - HUB 00 (Madrid CPD: 10.254.10.1, Spokes: .2-.254)",
    },
    {
        "prefix": "10.254.11.0/24",
        "status": "active",
        "role_slug": "cloud-transit-sdwan",
        "site_slug": "jesp",
        "description": "Overlay HubVPN - HUB 02 (JESP: 10.254.11.1, Spokes: .2-.254)",
    },
    {
        "prefix": "10.254.13.0/30",
        "status": "active",
        "role_slug": "inter-hub-transit",
        "description": "Enlace troncal directo Inter-Hub (HUB 00 .1 <-> HUB 02 .2)",
    },
    # BGP APIPA
    {
        "prefix": "169.254.239.4/30",
        "status": "active",
        "role_slug": "bgp-peering-apipa",
        "site_slug": "madrid-cpd",
        "description": "BGP AWS Peering Tunnel 1 (HUB 00 .6 <-> AWS TGW .5)",
    },
    {
        "prefix": "169.254.76.32/30",
        "status": "active",
        "role_slug": "bgp-peering-apipa",
        "site_slug": "madrid-cpd",
        "description": "BGP AWS Peering Tunnel 2 (HUB 00 .34 <-> AWS TGW .33)",
    },
    {
        "prefix": "169.254.21.0/30",
        "status": "active",
        "role_slug": "bgp-peering-apipa",
        "site_slug": "madrid-cpd",
        "description": "BGP Azure Peering Tunnel 1 (HUB 00 .2 <-> Azure VNG .1)",
    },
    # Pools VPN Dial-up
    {
        "prefix": "10.121.148.0/24",
        "status": "active",
        "role_slug": "vpn-dialup-pool",
        "site_slug": "madrid-cpd",
        "description": "VPN Dial-up: Usuarios Internos SSO SAML (HUB 00 Madrid CPD)",
    },
    {
        "prefix": "10.121.152.0/24",
        "status": "active",
        "role_slug": "vpn-dialup-pool",
        "site_slug": "jesp",
        "description": "VPN Dial-up: Usuarios Internos SSO SAML (HUB 02 JESP)",
    },
    {
        "prefix": "10.122.148.0/24",
        "status": "active",
        "role_slug": "vpn-dialup-pool",
        "site_slug": "madrid-cpd",
        "description": "VPN Dial-up: Proveedores y Externos Full-Tunnel (HUB 00 Madrid CPD)",
    },
    {
        "prefix": "10.122.152.0/24",
        "status": "active",
        "role_slug": "vpn-dialup-pool",
        "site_slug": "jesp",
        "description": "VPN Dial-up: Proveedores y Externos Full-Tunnel (HUB 02 JESP)",
    },
    {
        "prefix": "10.120.148.0/24",
        "status": "active",
        "role_slug": "vpn-dialup-pool",
        "site_slug": "madrid-cpd",
        "description": "VPN Dial-up: Proveedores Split-Tunnel (HUB 00 Madrid CPD)",
    },
    {
        "prefix": "10.120.152.0/24",
        "status": "active",
        "role_slug": "vpn-dialup-pool",
        "site_slug": "jesp",
        "description": "VPN Dial-up: Proveedores Split-Tunnel (HUB 02 JESP)",
    },
]

# 9. Prefijos específicos de Datacenters (Hubs)
HUB_SPECIFIC_PREFIXES: List[Dict[str, Any]] = [
    # Madrid CPD (HUB 00)
    {
        "prefix": "10.148.17.0/24",
        "status": "active",
        "role_slug": "lan-servidores",
        "site_slug": "madrid-cpd",
        "description": "Madrid CPD: Servidores centrales y servicios troncales",
    },
    {
        "prefix": "10.148.18.96/27",
        "status": "active",
        "role_slug": "b2b-extranet-nat",
        "site_slug": "madrid-cpd",
        "description": "Madrid CPD: Rango DNAT Local Bloque A (10.148.18.96 - 127) para terceros",
    },
    {
        "prefix": "10.148.18.128/25",
        "status": "active",
        "role_slug": "b2b-extranet-nat",
        "site_slug": "madrid-cpd",
        "description": "Madrid CPD: Rango DNAT Local Bloque B (10.148.18.128 - 255) para terceros",
    },
    # JESP (HUB 02)
    {
        "prefix": "10.152.17.0/24",
        "status": "active",
        "role_slug": "lan-servidores",
        "site_slug": "jesp",
        "description": "JESP: Servidores secundarios de contingencia y réplica",
    },
]
