"""`felcloud doctor` : vérifie que tout est prêt sur la machine."""

import shutil
import subprocess
import sys
from pathlib import Path

from felcloud import config, credentials, ui

PULUMI_FALLBACK = Path.home() / ".pulumi" / "bin" / "pulumi"

INSTALL_HINTS = {
    "terraform": "felcloud install terraform   (ou https://developer.hashicorp.com/terraform/install)",
    "pulumi": "felcloud install pulumi",
    "ssh": "sudo apt install openssh-client   (ou pacman -S openssh, dnf install openssh-clients ; "
           "déjà présent sur macOS)",
}


def find_tool(name):
    found = shutil.which(name)
    if found:
        return found
    if name == "terraform":
        local = Path.home() / ".local" / "bin" / "terraform"
        return str(local) if local.exists() else None
    if name == "pulumi" and PULUMI_FALLBACK.exists():
        return str(PULUMI_FALLBACK)
    return None


def tool_version(path):
    try:
        out = subprocess.run([path, "version"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "?"
    first = out.strip().splitlines()[0] if out.strip() else "?"
    return first.replace("Terraform ", "")


def run():
    ui.title("Vérification de l'environnement")
    problems = 0

    ui.section("Système")
    if sys.version_info >= (3, 10):
        ui.ok(f"Python {sys.version.split()[0]}")
    else:
        ui.err(f"Python {sys.version.split()[0]} : la version 3.10 minimum est requise")
        problems += 1
    ssh = find_tool("ssh")
    if ssh:
        ui.ok("Client SSH")
    else:
        ui.err("Client SSH absent")
        ui.hint(INSTALL_HINTS["ssh"])
        problems += 1

    ui.section("Identifiants")
    try:
        clouds = credentials.installed_clouds()
    except credentials.CloudsFileError as exc:
        ui.err(str(exc))
        clouds, problems = {}, problems + 1
    if clouds:
        ui.ok(f"{len(clouds)} cloud(s) dans {credentials.CLOUDS_FILE}")
        if credentials.is_protected():
            ui.ok("Fichier protégé (chmod 600)")
        else:
            ui.warn("Fichier lisible par d'autres utilisateurs : lance « felcloud setup » pour le protéger")
        default = config.default_cloud()
        if default and default in clouds:
            ui.ok(f"Cloud par défaut : {default}")
        else:
            ui.warn("Aucun cloud par défaut : lance « felcloud setup »")
    elif clouds == {}:
        ui.err("Aucun cloud configuré")
        ui.hint("Lance « felcloud setup »")
        problems += 1

    ui.section("Outils d'infrastructure (au moins un des deux)")
    available = 0
    for tool in ("terraform", "pulumi"):
        path = find_tool(tool)
        if path:
            available += 1
            ui.ok(f"{tool} {tool_version(path)}")
            if tool == "pulumi" and not shutil.which("pulumi"):
                ui.hint(f"Installé dans {path.rsplit('/', 1)[0]} mais la commande « pulumi » n'est pas "
                        "dans le PATH : lance « felcloud install pulumi » pour la rendre disponible")
        else:
            ui.warn(f"{tool} non installé")
            ui.hint(INSTALL_HINTS[tool])
    if not available:
        problems += 1

    ui.section("Langages pour Pulumi (seulement si tu les choisis)")
    for cmd, label, how in (("node", "Node.js — Pulumi (JavaScript)", "felcloud install node"),
                            ("go", "Go — Pulumi (Go)", "felcloud install go")):
        if find_tool(cmd):
            ui.ok(f"{label} : {tool_version(find_tool(cmd)) if cmd == 'go' else _node_version()}")
        else:
            ui.info(f"{label} : non installé")
            ui.hint(how)

    ui.console.print()
    if problems:
        ui.err(f"{problems} point(s) à corriger avant de continuer.")
    else:
        ui.ok("[bold]Tout est prêt.[/]")
    return problems


def _node_version():
    try:
        return subprocess.run([find_tool("node"), "--version"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "?"
