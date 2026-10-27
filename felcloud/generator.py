"""Transforme les réponses de l'assistant en projet prêt à l'emploi."""

import subprocess
from datetime import date
from importlib.resources import files
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from felcloud import doctor
from felcloud.wizard import SG_RULES

TEMPLATES = Path(str(files("felcloud") / "templates"))


def _env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


BRICK_DEFAULTS = {"network": None, "security_group": None, "keypair": None, "instances": [], "volumes": [],
                  "internet_proxy": None}

# Script de premier démarrage selon le rôle de la machine.
CLOUD_INIT_FILES = {
    "bastion": "cloud-init-bastion.yaml",   # IP publique + proxy Squid pour les autres
    "public": "cloud-init-public.yaml",     # IP publique, nginx
    "private": "cloud-init-private.yaml",   # pas d'IP publique : Internet via le proxy
}


def cloud_init_role(vm, proxy):
    """Rôle cloud-init d'une machine, ou None si elle n'a besoin d'aucun script."""
    if proxy and vm["name"] == proxy["bastion"]:
        return "bastion"
    if vm["floating_ip"]:
        return "public" if vm["nginx"] else None
    return "private" if proxy else None


def normalize(answers):
    """Les briques non choisies sont absentes des réponses : on leur donne une valeur vide."""
    a = dict(answers)
    for key, empty in BRICK_DEFAULTS.items():
        if a.get(key) is None:
            a[key] = empty
    return a


def build_context(a):
    """Valeurs dérivées des réponses, pour garder les templates simples."""
    vms = a.get("instances") or []
    net = a.get("network")
    kp = a.get("keypair")
    public = [vm for vm in vms if vm["floating_ip"]]

    if not net:
        net_id_ref = None
    elif net["mode"] == "create":
        net_id_ref = "openstack_networking_network_v2.main.id"
    else:
        net_id_ref = "data.openstack_networking_network_v2.main.id"

    if not kp:
        keypair_ref = None
    elif kp["mode"] == "existing":
        keypair_ref = '"' + kp["name"] + '"'
    else:
        keypair_ref = "openstack_compute_keypair_v2.main.name"

    sg = a.get("security_group")
    sg_summary = ""
    if sg:
        parts = [label.split(" (")[0].split(" —")[0] for key, label, _ in SG_RULES if key in sg["rules"]]
        parts += [f"TCP {p}" for p in sg["custom_tcp_ports"]]
        sg_summary = ", ".join(parts) or "aucune ouverture"

    proxy = a.get("internet_proxy")
    roles = {vm["name"]: cloud_init_role(vm, proxy) for vm in vms}

    # Machine de rebond SSH vers les machines privées : le bastion dédié s'il existe,
    # sinon celle qui héberge le proxy, sinon la première machine publique.
    dedicated = next((vm for vm in vms if vm.get("role") == "bastion"), None)
    proxy_vm = next((vm for vm in vms if proxy and vm["name"] == proxy["bastion"]), None)
    jump = dedicated or proxy_vm or (public[0] if public else {})

    tool = a.get("tool", "terraform")
    return {
        "a": a,
        "tool_label": {"terraform": "Terraform", "pulumi-python": "Pulumi (Python)",
                       "pulumi-javascript": "Pulumi (JavaScript)", "pulumi-go": "Pulumi (Go)"}.get(tool, tool),
        "main_file": PULUMI_FILES.get(tool, [""])[0],
        "proxy": proxy,
        "cloud_init": {name: CLOUD_INIT_FILES[r] if r else "" for name, r in roles.items()},
        "roles_used": sorted({r for r in roles.values() if r}),
        "bastion_nginx": bool(proxy_vm and proxy_vm["nginx"]),
        "private_nginx": any(vm["nginx"] for vm in vms if roles[vm["name"]] == "private"),
        "dedicated_bastion": dedicated,
        "net_id_ref": net_id_ref,
        "sg": bool(sg),
        "sg_summary": sg_summary,
        "keypair_ref": keypair_ref,
        "private_key": kp.get("private_key_path") if kp else "",
        "any_fip": bool(public),
        "jump": jump,
        "has_private_vms": len(public) < len(vms),
        "any_nginx": any(vm["nginx"] for vm in vms),
        "any_attached": any(v["attach_to"] for v in a.get("volumes") or []),
        "generated_on": date.today().strftime("%d/%m/%Y"),
    }


# Fichiers produits pour chaque langage Pulumi (le premier cité est le programme).
PULUMI_FILES = {
    "pulumi-python": ["__main__.py", "Pulumi.yaml", "requirements.txt"],
    "pulumi-javascript": ["index.js", "Pulumi.yaml", "package.json"],
    "pulumi-go": ["main.go", "Pulumi.yaml", "go.mod"],
}


def file_plan(a, ctx):
    """Liste (template, fichier produit) selon les briques choisies."""
    plan = [("common/README.md.j2", "README.md"), ("common/gitignore.j2", ".gitignore")]
    for role in ctx["roles_used"]:
        plan.append((f"common/{CLOUD_INIT_FILES[role]}.j2", CLOUD_INIT_FILES[role]))

    if a["tool"] == "terraform":
        plan += [("terraform/versions.tf.j2", "versions.tf"), ("terraform/provider.tf.j2", "provider.tf")]
        if a.get("network"):
            plan.append(("terraform/network.tf.j2", "network.tf"))
        if a.get("security_group"):
            plan.append(("terraform/security.tf.j2", "security.tf"))
        if a.get("keypair") and a["keypair"]["mode"] != "existing":
            plan.append(("terraform/keypair.tf.j2", "keypair.tf"))
        if a.get("instances"):
            plan.append(("terraform/instances.tf.j2", "instances.tf"))
        if a.get("volumes"):
            plan.append(("terraform/volumes.tf.j2", "volumes.tf"))
        if a.get("instances") or a.get("network"):
            plan.append(("terraform/outputs.tf.j2", "outputs.tf"))
    elif a["tool"] in PULUMI_FILES:
        plan += [(f"{a['tool']}/{name}.j2", name) for name in PULUMI_FILES[a["tool"]]]
    else:
        raise NotImplementedError(f"Outil pas encore pris en charge : {a['tool']}")
    return plan


def ensure_ssh_key(a):
    """Crée la clé SSH dédiée si l'utilisateur l'a demandé et qu'elle n'existe pas encore."""
    kp = a.get("keypair")
    if not kp or kp["mode"] != "generate":
        return None
    private = Path(kp["private_key_path"]).expanduser()
    if private.exists():
        return None
    private.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", f"felcloud-{a['project']}", "-f", str(private)],
        check=True, capture_output=True,
    )
    return private


def generate(a, dest):
    """Écrit le projet dans `dest` (qui ne doit pas exister) et retourne la liste des fichiers."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"Le dossier {dest} existe déjà et n'est pas vide.")
    env = _env()
    ctx = build_context(normalize(a))
    rendered = {output: env.get_template(template).render(**ctx)
                for template, output in file_plan(ctx["a"], ctx)}
    rendered["felcloud.yaml"] = (
        "# Réponses données à `felcloud new`. Regénérer : felcloud new --answers felcloud.yaml\n"
        + yaml.safe_dump(a, sort_keys=False, allow_unicode=True)
    )

    dest.mkdir(parents=True, exist_ok=True)
    for output, content in rendered.items():
        (dest / output).write_text(content)
    written = list(rendered)

    if a["tool"].startswith("pulumi"):
        # Dossier de l'état Pulumi (backend local déclaré dans Pulumi.yaml).
        (dest / ".pulumi-state").mkdir(exist_ok=True)
    if a["tool"] == "pulumi-go" and doctor.find_tool("gofmt"):
        subprocess.run([doctor.find_tool("gofmt"), "-w", "main.go"], cwd=dest, capture_output=True)
    if a["tool"] == "terraform":
        terraform = doctor.find_tool("terraform")
        if terraform:
            subprocess.run([terraform, "fmt", "-list=false"], cwd=dest, capture_output=True)
    return sorted(written)
