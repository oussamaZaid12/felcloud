"""Lancer Terraform ou Pulumi dans un projet généré, et vérifier que les machines répondent."""

import json
import os
import re
import shlex
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from felcloud import doctor, ui

SSH_WAIT_SECONDS = 360
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]

PLAN_FILE = "felcloud.tfplan"
PULUMI_STACK = "dev"
INSTALL_HINT = {"terraform": "felcloud install terraform", "pulumi": "felcloud install pulumi",
                "go": "felcloud install go", "node": "felcloud install node"}


def tool_of(project_dir):
    """« terraform » ou « pulumi », d'après les réponses enregistrées du projet."""
    answers_file = Path(project_dir) / "felcloud.yaml"
    if answers_file.exists():
        tool = (yaml.safe_load(answers_file.read_text()) or {}).get("tool", "")
        return "pulumi" if tool.startswith("pulumi") else "terraform"
    return "pulumi" if (Path(project_dir) / "Pulumi.yaml").exists() else "terraform"


def pulumi_env():
    """Le projet ne stocke aucun secret : phrase de passe vide, pour que Pulumi ne la demande pas."""
    env = dict(os.environ)
    env.setdefault("PULUMI_CONFIG_PASSPHRASE", "")
    env["PULUMI_SKIP_UPDATE_CHECK"] = "true"
    return env


def _binary(tool):
    path = doctor.find_tool(tool)
    if not path:
        ui.err(f"{tool.capitalize()} n'est pas installé.")
        ui.hint(f"Installe-le avec : {INSTALL_HINT[tool]}")
    return path


def _run(binary, args, cwd, tool, quiet=False):
    ui.console.print(f"\n[bold #2e86de]$ {tool} {' '.join(args)}[/]")
    env = pulumi_env() if tool == "pulumi" else None
    if quiet:
        res = subprocess.run([binary] + args, cwd=cwd, env=env, capture_output=True, text=True)
        if res.returncode:
            ui.console.print(res.stdout[-2000:] + res.stderr[-2000:])
        return res.returncode == 0
    return subprocess.run([binary] + args, cwd=cwd, env=env).returncode == 0


def preview(project_dir):
    """Aperçu : rien n'est créé. Terraform enregistre le plan pour qu'apply fasse exactement la même chose."""
    tool = tool_of(project_dir)
    binary = _binary(tool)
    if not binary:
        return False
    if tool == "terraform":
        steps = [(["init", "-input=false"], False), (["plan", "-input=false", f"-out={PLAN_FILE}"], False)]
    else:
        ui.hint("Première fois : installation des bibliothèques du programme (une à deux minutes).")
        if (Path(project_dir) / "go.mod").exists():
            go = _binary("go")
            if not go or not _run(go, ["mod", "tidy"], project_dir, "go", quiet=True):
                ui.err("go mod tidy a échoué (voir le message ci-dessus).")
                return False
        steps = [(["install"], True), (["stack", "select", "--create", PULUMI_STACK], True),
                 (["preview"], False)]
    for args, quiet in steps:
        if not _run(binary, args, project_dir, tool, quiet=quiet):
            ui.err(f"{tool} {args[0]} a échoué (voir le message ci-dessus).")
            return False
    ui.ok("Aperçu terminé : rien n'a encore été créé.")
    return True


def apply(project_dir):
    tool = tool_of(project_dir)
    binary = _binary(tool)
    if not binary:
        return False
    if tool == "terraform":
        ok = _run(binary, ["apply", "-input=false", PLAN_FILE], project_dir, tool)
        Path(project_dir, PLAN_FILE).unlink(missing_ok=True)
    else:
        ok = _run(binary, ["up", "--yes", "--skip-preview"], project_dir, tool)
    if not ok:
        ui.err(f"La création a échoué (voir le message ci-dessus). Relance-la depuis le dossier "
               f"du projet : {'terraform apply' if tool == 'terraform' else 'pulumi up'}")
        return False
    ui.ok("Infrastructure créée.")
    return True


def destroy(project_dir):
    tool = tool_of(project_dir)
    binary = _binary(tool)
    if not binary:
        return False
    args = ["destroy", "-auto-approve", "-input=false"] if tool == "terraform" else \
        ["destroy", "--yes", "--skip-preview"]
    return _run(binary, args, project_dir, tool)


def project_outputs(project_dir):
    """Les sorties du projet (adresses, commandes SSH), quel que soit l'outil."""
    tool = tool_of(project_dir)
    binary = doctor.find_tool(tool)
    if not binary:
        return {}
    if tool == "terraform":
        out = subprocess.run([binary, "output", "-json"], cwd=project_dir, capture_output=True, text=True)
        if out.returncode:
            return {}
        return {k: v.get("value") for k, v in json.loads(out.stdout or "{}").items()}
    out = subprocess.run([binary, "stack", "output", "--json", "--stack", PULUMI_STACK], cwd=project_dir,
                         env=pulumi_env(), capture_output=True, text=True)
    if out.returncode:
        return {}
    return json.loads(out.stdout or "{}")


def _port_open(ip, port=22):
    try:
        with socket.create_connection((ip, port), timeout=5):
            return True
    except OSError:
        return False


def _check_one(name, command, deadline):
    """Attend que le port 22 réponde, puis teste une vraie connexion avec la clé."""
    args = shlex.split(command)
    target = args[-1]
    ip = target.split("@")[-1]
    via_jump = "-o" in args and any(a.startswith("ProxyCommand=") for a in args)
    if not via_jump:
        while not _port_open(ip):
            if time.time() > deadline:
                return name, "unreachable", ""
            time.sleep(10)
    while True:
        cmd = [args[0]] + SSH_OPTS + args[1:] + ["true"]
        if via_jump:
            cmd = [a.replace("ssh -i", "ssh " + " ".join(SSH_OPTS) + " -i", 1) if a.startswith("ProxyCommand=")
                   else a for a in cmd]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            return name, "ok", ""
        if "Permission denied" in res.stderr and time.time() > deadline - SSH_WAIT_SECONDS + 240:
            return name, "denied", res.stderr.strip()
        if time.time() > deadline:
            return name, "timeout", res.stderr.strip()
        time.sleep(10)


def project_ips(outputs):
    ips = set()
    for vm in (outputs.get("machines") or {}).values():
        ips.update(ip for ip in (vm.get("ip_publique"), vm.get("ip_privee")) if ip and ip != "aucune")
    return ips


def forget_host_keys(ips):
    """FelCloud réutilise les IP publiques (et deux projets peuvent avoir les mêmes IP
    privées) : on efface les empreintes mémorisées pour d'anciennes machines, sinon SSH
    refuse la connexion avec « REMOTE HOST IDENTIFICATION HAS CHANGED »."""
    for ip in ips:
        subprocess.run(["ssh-keygen", "-R", ip], capture_output=True)


def check_connectivity(project_dir):
    """Vérifie, juste après la création, que chaque machine est joignable en SSH.

    Retourne True si tout répond. Affiche un diagnostic compréhensible sinon.
    """
    outputs = project_outputs(project_dir)
    forget_host_keys(project_ips(outputs))
    commands = {**(outputs.get("ssh") or {}), **(outputs.get("ssh_via_rebond") or {})}
    if not commands:
        ui.info("Aucune machine joignable depuis ta machine (pas d'IP publique) : pas de test SSH.")
        return True
    for cmd in commands.values():
        if "<ta-clé-privée>" in cmd:
            ui.info("Clé SSH déjà présente sur le cloud : test SSH impossible sans sa clé privée.")
            return True

    ui.section("Vérification de la connexion SSH")
    ui.hint("Les machines démarrent (installation des paquets comprise) : compte 2 à 5 minutes.")
    deadline = time.time() + SSH_WAIT_SECONDS
    public = outputs.get("ssh") or {}
    with ui.console.status("Attente des machines..."):
        with ThreadPoolExecutor(max_workers=8) as pool:
            # Les machines publiques d'abord : les machines privées passent par elles.
            results = list(pool.map(lambda kv: _check_one(kv[0], kv[1], deadline), public.items()))
            private = {k: v for k, v in commands.items() if k not in public}
            if all(status == "ok" for _, status, _ in results):
                results += list(pool.map(lambda kv: _check_one(kv[0], kv[1], deadline), private.items()))
            else:
                results += [(name, "skipped", "") for name in private]

    all_ok = True
    for name, status, detail in results:
        if status == "ok":
            ui.ok(f"{name} : connexion SSH réussie")
            continue
        all_ok = False
        if status == "unreachable":
            ui.err(f"{name} : aucune réponse sur le port 22 après {SSH_WAIT_SECONDS // 60} minutes")
            ui.hint("Le pare-feu autorise SSH ? (règle « SSH » cochée) Si oui, le chemin réseau vers "
                    "l'IP publique est en panne côté FelCloud, en général le routeur.")
            ui.hint("Si tu as choisi un réseau EXISTANT, regénère le projet avec « Créer un nouveau "
                    "réseau » ; sinon, signale-le au support FelCloud avec l'IP concernée.")
        elif status == "denied":
            ui.err(f"{name} : la machine répond mais refuse la clé SSH")
            ui.hint("Utilise exactement la commande de « terraform output ssh » (bonne clé, bon "
                    "utilisateur). Si elle échoue aussi, recrée la machine : terraform apply "
                    f"-replace='openstack_compute_instance_v2.vm[\"{name}\"]'")
        elif status == "skipped":
            ui.warn(f"{name} : non testée (la machine de rebond ne répond pas)")
        else:
            ui.err(f"{name} : pas de connexion après {SSH_WAIT_SECONDS // 60} minutes")
            ui.hint(re.sub(r"\s+", " ", detail)[:200] or "Réessaie dans quelques minutes : felcloud test")
    if all_ok:
        ui.ok("[bold]Toutes les machines répondent en SSH.[/]")
        if any((project_dir / f).exists() for f in ("cloud-init-bastion.yaml", "cloud-init-private.yaml",
                                                   "cloud-init-public.yaml")):
            ui.hint("Les installations automatiques (proxy, nginx) peuvent encore tourner quelques "
                    "minutes. Sur une machine : cloud-init status --wait")
    return all_ok
