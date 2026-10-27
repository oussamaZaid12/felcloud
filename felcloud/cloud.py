"""Connexion à OpenStack et lecture des ressources disponibles sur le projet."""

import logging
import warnings
from dataclasses import dataclass, field

for _name in ("openstack", "keystoneauth", "stevedore", "urllib3"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")


@dataclass
class CheckResult:
    ok: bool
    cloud: str
    error: str = ""
    project_id: str = ""
    region: str = ""
    usage: dict = field(default_factory=dict)


def connect(cloud):
    import openstack

    return openstack.connect(cloud=cloud)


def explain(exc):
    """Traduit une erreur d'authentification en message compréhensible."""
    raw = str(exc)
    low = raw.lower()
    if "could not find application credential" in low:
        return ("Cette application credential n'existe plus (supprimée ou expirée). "
                "Crée-en une nouvelle sur le portail et réimporte le clouds.yaml.")
    if "401" in raw or "unauthorized" in low or "invalid application credential" in low:
        return "Identifiants refusés : le secret est incorrect ou a été modifié."
    if "cloud" in low and "not found" in low and "config" in low:
        return "Ce nom de cloud n'existe pas dans ~/.config/openstack/clouds.yaml."
    if any(k in low for k in ("name or service not known", "failed to resolve", "connection refused",
                              "max retries exceeded", "timed out", "unable to establish connection")):
        return ("Impossible de joindre l'adresse d'authentification (auth_url). "
                "Vérifie ta connexion Internet, ou ton VPN si le cloud est interne.")
    if "certificate" in low or "ssl" in low:
        return ("Erreur de certificat HTTPS. Si ton fournisseur t'a donné un fichier .crt, "
                "ajoute `cacert: /chemin/vers/le.crt` dans l'entrée du clouds.yaml.")
    return raw.splitlines()[0][:300]


@dataclass
class Flavor:
    name: str
    vcpus: int
    ram_mb: int
    disk_gb: int

    @property
    def label(self):
        return f"{self.name:22} {self.vcpus} vCPU · {self.ram_mb // 1024} Go RAM · {self.disk_gb} Go disque"


@dataclass
class Discovery:
    """Tout ce que l'assistant a besoin de connaître du projet, lu en une fois."""
    flavors: list
    images: list
    external_networks: list
    project_networks: list
    keypairs: list
    volume_types: list
    limits: dict


# Utilisateur SSH par défaut des images cloud officielles, déduit du nom de l'image.
SSH_USERS = [
    ("ubuntu", "ubuntu"), ("debian", "debian"), ("rocky", "rocky"), ("alma", "almalinux"),
    ("centos", "cloud-user"), ("coreos", "core"), ("fedora", "fedora"), ("arch", "arch"),
    ("freebsd", "freebsd"), ("openbsd", "openbsd"), ("netbsd", "root"), ("cirros", "cirros"),
]


def ssh_user_for(image_name):
    low = image_name.lower()
    return next((user for key, user in SSH_USERS if key in low), "")


def is_apt_based(image_name):
    low = image_name.lower()
    return "ubuntu" in low or "debian" in low


def _image_rank(name):
    """Ubuntu LTS récentes d'abord, puis Debian, puis le reste par ordre alphabétique."""
    low = name.lower()
    if "ubuntu" in low:
        return (0, [-ord(c) for c in low])
    if "debian" in low:
        return (1, [-ord(c) for c in low])
    return (2, low)


def discover(conn):
    project = conn.current_project_id
    flavors = sorted(
        (Flavor(f.name, f.vcpus, f.ram, f.disk) for f in conn.compute.flavors(details=True)),
        key=lambda f: (f.name.split(".")[1] if f.name.count(".") >= 2 else f.name, f.vcpus, f.ram_mb),
    )
    images = sorted((i.name for i in conn.image.images(status="active")), key=_image_rank)

    # Routeurs reliés à l'extérieur, et réseaux sur lesquels ils sont branchés : sans un
    # tel routeur, un réseau existant ne peut pas recevoir d'IP publique.
    routed = {}
    for router in conn.network.routers(project_id=project):
        if not router.external_gateway_info:
            continue
        for port in conn.network.ports(device_id=router.id):
            if port.device_owner.startswith("network:router_interface"):
                routed.setdefault(port.network_id, router.name)

    external, internal = [], []
    for net in conn.network.networks():
        if net.is_router_external:
            external.append({"name": net.name, "id": net.id, "subnet_ids": list(net.subnet_ids)})
        elif net.project_id == project:
            subnets = [conn.network.get_subnet(s) for s in net.subnet_ids]
            internal.append({"name": net.name, "id": net.id, "router": routed.get(net.id),
                             "cidrs": [s.cidr for s in subnets if s.ip_version == 4]})
    external.sort(key=lambda n: (n["name"].upper() not in ("INTERNET", "PUBLIC", "EXTERNAL"), n["name"]))

    limits = {}
    try:
        compute = conn.get_compute_limits()
        limits["instances"] = (compute.total_instances_used, compute.max_total_instances)
        limits["cores"] = (compute.total_cores_used, compute.max_total_cores)
        limits["ram_mb"] = (compute.total_ram_used, compute.max_total_ram_size)
    except Exception:
        pass
    try:
        quota = conn.network.get_quota(project, details=True)
        limits["floating_ips"] = (quota.floating_ips["used"], quota.floating_ips["limit"])
    except Exception:
        pass
    try:
        absolute = conn.block_storage.get_limits().absolute
        limits["volumes"] = (absolute.total_volumes_used, absolute.max_total_volumes)
        limits["volume_gb"] = (absolute.total_gigabytes_used, absolute.max_total_volume_gigabytes)
    except Exception:
        pass

    try:
        volume_types = sorted(t.name for t in conn.block_storage.types())
    except Exception:
        volume_types = []

    return Discovery(
        flavors=flavors,
        images=images,
        external_networks=external,
        project_networks=internal,
        keypairs=sorted(k.name for k in conn.compute.keypairs()),
        volume_types=volume_types,
        limits=limits,
    )


def check(cloud):
    """Teste l'authentification et récupère un aperçu du projet."""
    try:
        conn = connect(cloud)
        conn.authorize()
        result = CheckResult(
            ok=True,
            cloud=cloud,
            project_id=conn.current_project_id or "",
            region=conn.config.get_region_name() or "",
        )
    except Exception as exc:
        return CheckResult(ok=False, cloud=cloud, error=explain(exc))

    try:
        limits = conn.get_compute_limits()
        result.usage = {
            "Instances": (limits.total_instances_used, limits.max_total_instances),
            "vCPU": (limits.total_cores_used, limits.max_total_cores),
            "RAM (Go)": (limits.total_ram_used // 1024, limits.max_total_ram_size // 1024),
        }
    except Exception:
        pass
    return result
