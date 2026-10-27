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


PROJECTS_DIR = Path.home() / "felcloud-projets"


def known_projects():
    """Projets créés hors de ~/felcloud-projets (avec --output), mémorisés à la création."""
    return [Path(p) for p in load().get("projects", [])]


def remember_project(path):
    path = Path(path).resolve()
    if path.parent == PROJECTS_DIR.resolve():
        return
    data = load()
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
