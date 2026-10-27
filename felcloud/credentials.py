"""Lecture, import et protection du fichier clouds.yaml.

Le fichier standard d'OpenStack est ~/.config/openstack/clouds.yaml. Terraform,
Pulumi, la commande `openstack` et cet outil le lisent tous au même endroit.
"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

# OS_CLIENT_CONFIG_FILE est la variable standard d'OpenStack pour pointer vers un autre fichier.
CLOUDS_FILE = Path(
    os.environ.get("OS_CLIENT_CONFIG_FILE", Path.home() / ".config" / "openstack" / "clouds.yaml")
).expanduser()
CLOUDS_DIR = CLOUDS_FILE.parent

FELCLOUD_AUTH_URL = "https://identity.api.felcloud.io/v3/"
FELCLOUD_REGION = "North-Africa"

DOWNLOAD_DIRS = [Path.home() / "Téléchargements", Path.home() / "Downloads"]


class CloudsFileError(Exception):
    pass


def read_document(path):
    """Retourne le document YAML complet, après avoir vérifié qu'il contient `clouds:`."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise CloudsFileError(f"Fichier introuvable : {path}")
    try:
        doc = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise CloudsFileError(f"Le fichier n'est pas un YAML valide : {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("clouds"), dict) or not doc["clouds"]:
        raise CloudsFileError(
            "Le fichier ne contient pas de section « clouds: ». "
            "Vérifie que c'est bien le clouds.yaml téléchargé depuis le portail."
        )
    return doc


def installed_document():
    if not CLOUDS_FILE.exists():
        return {"clouds": {}}
    return read_document(CLOUDS_FILE)


def installed_clouds():
    return installed_document()["clouds"]


def find_downloaded_files():
    """clouds.yaml récemment téléchargés, du plus récent au plus ancien."""
    found = []
    for directory in DOWNLOAD_DIRS:
        if directory.is_dir():
            found += [p for p in directory.glob("clouds*.yaml") if p.is_file()]
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def auth_kind(entry):
    auth_type = entry.get("auth_type", "password")
    if "applicationcredential" in auth_type:
        return "application credential"
    if auth_type in ("password", "v3password"):
        return "mot de passe"
    return auth_type


def missing_secret(entry):
    """Message explicatif si l'entrée ne contient pas de quoi s'authentifier, sinon None."""
    auth = entry.get("auth") or {}
    if not auth.get("auth_url"):
        return "pas d'adresse d'authentification (auth_url)"
    kind = auth_kind(entry)
    if kind == "application credential":
        if not (auth.get("application_credential_id") or auth.get("application_credential_name")):
            return "identifiant de l'application credential absent"
        if not auth.get("application_credential_secret"):
            return "secret de l'application credential absent"
    elif kind == "mot de passe" and not auth.get("password"):
        return (
            "le mot de passe n'est pas dans le fichier (le portail ne l'inclut jamais). "
            "Crée plutôt une application credential : voir le README"
        )
    return None


def describe(entry):
    auth = entry.get("auth") or {}
    url = auth.get("auth_url", "")
    return {
        "type": auth_kind(entry),
        "endpoint": urlparse(url).hostname or url,
        "region": entry.get("region_name", "—"),
    }


def is_protected():
    if not CLOUDS_FILE.exists():
        return True
    return (CLOUDS_FILE.stat().st_mode & 0o077) == 0


def protect():
    """Rend le fichier lisible par son seul propriétaire (chmod 600)."""
    CLOUDS_DIR.chmod(0o700)
    if CLOUDS_FILE.exists():
        CLOUDS_FILE.chmod(0o600)


def _write_document(doc):
    CLOUDS_DIR.mkdir(parents=True, exist_ok=True)
    backup = None
    if CLOUDS_FILE.exists():
        backup = CLOUDS_FILE.with_name(f"clouds.yaml.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(CLOUDS_FILE, backup)
        backup.chmod(0o600)

    fd, tmp = tempfile.mkstemp(dir=CLOUDS_DIR, prefix=".clouds-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as handle:
            yaml.safe_dump(doc, handle, sort_keys=False, allow_unicode=True, default_flow_style=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CLOUDS_FILE)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    protect()
    return backup


def import_clouds(source_doc, resolve_conflict):
    """Ajoute les clouds de `source_doc` au clouds.yaml installé, sans rien écraser d'office.

    `resolve_conflict(name)` est appelé quand un cloud du même nom existe avec un contenu
    différent. Il renvoie le nom sous lequel enregistrer (le même nom = remplacer),
    ou None pour ignorer ce cloud.

    Retourne (noms_ajoutés, noms_déjà_identiques, chemin_de_sauvegarde).
    """
    target = installed_document()
    added, unchanged = [], []
    for name, entry in source_doc["clouds"].items():
        existing = target["clouds"].get(name)
        if existing == entry:
            unchanged.append(name)
            continue
        final_name = name if existing is None else resolve_conflict(name)
        if final_name is None:
            continue
        target["clouds"][final_name] = entry
        added.append(final_name)

    backup = _write_document(target) if added else None
    return added, unchanged, backup


def application_credential_entry(auth_url, region, credential_id, secret):
    """Entrée clouds.yaml identique à celle que produit le portail."""
    return {
        "auth": {
            "auth_url": auth_url,
            "application_credential_id": credential_id,
            "application_credential_secret": secret,
        },
        "region_name": region,
        "interface": "public",
        "identity_api_version": 3,
        "auth_type": "v3applicationcredential",
    }


def free_name(base):
    clouds = installed_clouds()
    if base not in clouds:
        return base
    index = 2
    while f"{base}-{index}" in clouds:
        index += 1
    return f"{base}-{index}"
