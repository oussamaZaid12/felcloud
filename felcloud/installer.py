"""`felcloud install <outil>` : installe Terraform, Pulumi, Go ou Node.js sans droits administrateur."""

import hashlib
import io
import json
import platform
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from felcloud import ui

BIN_DIR = Path.home() / ".local" / "bin"
RELEASES = "https://releases.hashicorp.com/terraform"
ARCHS = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def _get(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def install_terraform():
    arch = ARCHS.get(platform.machine().lower())
    if not arch:
        ui.err(f"Architecture non prise en charge : {platform.machine()}")
        return 1

    with ui.console.status("Recherche de la dernière version de Terraform..."):
        version = json.loads(_get("https://checkpoint-api.hashicorp.com/v1/check/terraform"))[
            "current_version"]
    archive_name = f"terraform_{version}_linux_{arch}.zip"

    with ui.console.status(f"Téléchargement de Terraform {version}..."):
        archive = _get(f"{RELEASES}/{version}/{archive_name}")
        sums = _get(f"{RELEASES}/{version}/terraform_{version}_SHA256SUMS").decode()

    expected = next((line.split()[0] for line in sums.splitlines()
                     if line.endswith(archive_name)), None)
    if hashlib.sha256(archive).hexdigest() != expected:
        ui.err("La somme de contrôle ne correspond pas : téléchargement corrompu, installation annulée.")
        return 1
    ui.ok("Somme de contrôle SHA-256 vérifiée")

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / "terraform"
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        target.write_bytes(zf.read("terraform"))
    target.chmod(0o755)
    ui.ok(f"Terraform {version} installé dans {target}")
    return 0


PULUMI_HOME = Path.home() / ".pulumi"
PULUMI_ARCHS = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def install_pulumi():
    """Installe le CLI Pulumi dans ~/.pulumi/bin (emplacement officiel), sans sudo, et le
    rend accessible depuis ~/.local/bin."""
    arch = PULUMI_ARCHS.get(platform.machine().lower())
    if not arch:
        ui.err(f"Architecture non prise en charge : {platform.machine()}")
        return 1

    with ui.console.status("Recherche de la dernière version de Pulumi..."):
        version = _get("https://www.pulumi.com/latest-version").decode().strip().lstrip("v")
    archive_name = f"pulumi-v{version}-linux-{arch}.tar.gz"

    with ui.console.status(f"Téléchargement de Pulumi {version} (environ 100 Mo)..."):
        archive = _get(f"https://get.pulumi.com/releases/sdk/{archive_name}")
        sums = _get(f"https://github.com/pulumi/pulumi/releases/download/v{version}/"
                    f"pulumi-{version}-checksums.txt").decode()

    expected = next((line.split()[0] for line in sums.splitlines() if line.endswith(archive_name)), None)
    if hashlib.sha256(archive).hexdigest() != expected:
        ui.err("La somme de contrôle ne correspond pas : téléchargement corrompu, installation annulée.")
        return 1
    ui.ok("Somme de contrôle SHA-256 vérifiée")

    bin_dir = PULUMI_HOME / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            # L'archive contient pulumi/<binaire> : on aplatit dans ~/.pulumi/bin.
            if member.isfile() and member.name.startswith("pulumi/"):
                member.name = member.name.split("/", 1)[1]
                tar.extract(member, bin_dir, filter="data")
                (bin_dir / member.name).chmod(0o755)
    ui.ok(f"Pulumi {version} installé dans {bin_dir}")
    link_pulumi()
    return 0


def link_pulumi():
    """Lien ~/.local/bin/pulumi → ~/.pulumi/bin/pulumi, pour que la commande `pulumi`
    fonctionne dans tous les terminaux (~/.local/bin est déjà dans le PATH de felcloud)."""
    source = PULUMI_HOME / "bin" / "pulumi"
    link = BIN_DIR / "pulumi"
    if not source.exists() or link.exists() or link.is_symlink():
        return
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)
    ui.ok(f"Commande pulumi disponible : {link}")


TOOLCHAINS_DIR = Path.home() / ".local" / "share" / "felcloud" / "toolchains"


def _verified_download(url, expected_sha256, label):
    with ui.console.status(f"Téléchargement de {label}..."):
        data = _get(url)
    if not expected_sha256 or hashlib.sha256(data).hexdigest() != expected_sha256:
        ui.err("La somme de contrôle ne correspond pas : téléchargement corrompu, installation annulée.")
        return None
    ui.ok("Somme de contrôle SHA-256 vérifiée")
    return data


def _extract_tar(data, target):
    """Extrait l'archive dans `target` en retirant son dossier racine (go/, node-vX/...)."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            parts = member.name.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            member.name = parts[1]
            tar.extract(member, target, filter="tar")


def _link(names, source_dir):
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        link = BIN_DIR / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(source_dir / name)
    ui.ok(f"Commandes disponibles dans {BIN_DIR} : {', '.join(names)}")


def install_go():
    """Go est nécessaire pour les projets Pulumi (Go)."""
    arch = ARCHS.get(platform.machine().lower())
    if not arch:
        ui.err(f"Architecture non prise en charge : {platform.machine()}")
        return 1
    with ui.console.status("Recherche de la dernière version de Go..."):
        release = next(r for r in json.loads(_get("https://go.dev/dl/?mode=json")) if r["stable"])
    archive = next(f for f in release["files"]
                   if f["os"] == "linux" and f["arch"] == arch and f["kind"] == "archive")
    data = _verified_download(f"https://go.dev/dl/{archive['filename']}", archive["sha256"],
                              f"{release['version']} (environ 70 Mo)")
    if data is None:
        return 1
    target = TOOLCHAINS_DIR / "go"
    _extract_tar(data, target)
    ui.ok(f"{release['version']} installé dans {target}")
    _link(["go", "gofmt"], target / "bin")
    return 0


NODE_ARCHS = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def install_node():
    """Node.js est nécessaire pour les projets Pulumi (JavaScript). Version LTS."""
    arch = NODE_ARCHS.get(platform.machine().lower())
    if not arch:
        ui.err(f"Architecture non prise en charge : {platform.machine()}")
        return 1
    with ui.console.status("Recherche de la dernière version LTS de Node.js..."):
        release = next(r for r in json.loads(_get("https://nodejs.org/dist/index.json")) if r["lts"])
    version = release["version"]
    filename = f"node-{version}-linux-{arch}.tar.gz"
    sums = _get(f"https://nodejs.org/dist/{version}/SHASUMS256.txt").decode()
    expected = next((line.split()[0] for line in sums.splitlines() if line.endswith(filename)), None)
    data = _verified_download(f"https://nodejs.org/dist/{version}/{filename}", expected,
                              f"Node.js {version} (environ 50 Mo)")
    if data is None:
        return 1
    target = TOOLCHAINS_DIR / "node"
    _extract_tar(data, target)
    ui.ok(f"Node.js {version} installé dans {target}")
    _link(["node", "npm", "npx"], target / "bin")
    return 0


INSTALLERS = {"terraform": install_terraform, "pulumi": install_pulumi, "go": install_go, "node": install_node}
