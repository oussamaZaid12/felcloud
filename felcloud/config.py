"""Préférences de l'outil (cloud par défaut), dans ~/.config/felcloud/config.yaml."""

from pathlib import Path

import yaml

CONFIG_FILE = Path.home() / ".config" / "felcloud" / "config.yaml"


def load():
    if not CONFIG_FILE.exists():
        return {}
    return yaml.safe_load(CONFIG_FILE.read_text()) or {}


def save(data):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


DEFAULT_PROJECTS_DIR = Path.home() / "felcloud-projets"


def projects_dir():
    """Dossier où sont rangés tous les projets, choisi par l'utilisateur (felcloud setup)."""
    chosen = load().get("projects_dir")
    return Path(chosen) if chosen else DEFAULT_PROJECTS_DIR


def projects_dir_chosen():
    return bool(load().get("projects_dir"))


def set_projects_dir(path):
    """Change le dossier des projets. Ceux de l'ancien dossier restent connus là où ils sont."""
    path = Path(path).expanduser().resolve()
    old = projects_dir()
    if old.is_dir() and old.resolve() != path:
        for project in old.iterdir():
            if (project / "felcloud.yaml").exists():
                remember_project(project)
    path.mkdir(parents=True, exist_ok=True)
    data = load()
    data["projects_dir"] = str(path)
    save(data)
    return path


def known_projects():
    """Projets créés hors du dossier des projets (avec --output), mémorisés à la création."""
    return [Path(p) for p in load().get("projects", [])]


def remember_project(path):
    path = Path(path).resolve()
    data = load()
    if path.parent == projects_dir().resolve():
        return
    paths = data.get("projects", [])
    if str(path) not in paths:
        data["projects"] = paths + [str(path)]
        save(data)


def forget_project(path):
    data = load()
    paths = [p for p in data.get("projects", []) if p != str(Path(path).resolve())]
    if paths != data.get("projects", []):
        data["projects"] = paths
        save(data)


def default_cloud():
    return load().get("default_cloud")


def set_default_cloud(name):
    data = load()
    data["default_cloud"] = name
    save(data)
