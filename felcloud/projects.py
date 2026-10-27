"""`felcloud projets` et `felcloud destroy` : retrouver, inspecter et supprimer ses projets."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml
from rich.table import Table

from felcloud import config, doctor, ui

# Linux, puis macOS (où /tmp pointe vers /private/tmp et le dossier temporaire
# de l'utilisateur est sous /private/var/folders).
TEMP_ROOTS = ("/tmp", "/var/tmp", "/dev/shm", "/private/tmp", "/private/var/tmp", "/private/var/folders")


@dataclass
class Project:
    path: Path
    answers: dict

    @property
    def name(self):
        return self.answers.get("project", self.path.name)

    @property
    def is_pulumi(self):
        return str(self.answers.get("tool", "")).startswith("pulumi")

    def state(self):
        """Ressources réellement créées, lues dans l'état local (sans appeler le cloud).

        Chaque élément est un dict avec au moins la clé "type"."""
        try:
            if self.is_pulumi:
                resources = []
                for f in (self.path / ".pulumi-state").glob(".pulumi/stacks/**/*.json"):
                    data = json.loads(f.read_text())
                    resources += [r for r in ((data.get("checkpoint") or {}).get("latest") or {})
                                  .get("resources") or [] if not r["type"].startswith("pulumi:")]
                return resources
            tfstate = self.path / "terraform.tfstate"
            if not tfstate.exists():
                return []
            data = json.loads(tfstate.read_text())
        except (OSError, ValueError):
            return []
        return [r for r in data.get("resources", []) if r.get("mode") == "managed"
                for _ in r.get("instances", [])]

    def summary(self):
        resources = self.state()
        vms = [r for r in resources
               if r["type"] in ("openstack_compute_instance_v2", "openstack:compute/instance:Instance")]
        return len(resources), len(vms)


def is_temporary(path):
    path = str(Path(path).resolve())
    return any(path == root or path.startswith(root + "/") for root in TEMP_ROOTS)


def all_projects():
    """Projets du dossier des projets + ceux créés ailleurs et mémorisés."""
    candidates = []
    folder = config.projects_dir()
    if folder.is_dir():
        candidates += sorted(p for p in folder.iterdir() if p.is_dir())
    candidates += config.known_projects()
    found, seen = [], set()
    for path in candidates:
        path = path.resolve()
        answers_file = path / "felcloud.yaml"
        if path in seen or not answers_file.exists():
            continue
        seen.add(path)
        try:
            answers = yaml.safe_load(answers_file.read_text()) or {}
        except yaml.YAMLError:
            answers = {}
        found.append(Project(path, answers))
    return found


def missing_known_projects():
    return [p for p in config.known_projects() if not (p / "felcloud.yaml").exists()]


def find(target):
    """Retrouve un projet par son nom ou par son chemin."""
    path = Path(target).expanduser()
    if (path / "felcloud.yaml").exists():
        return Project(path.resolve(), yaml.safe_load((path / "felcloud.yaml").read_text()) or {})
    matches = [p for p in all_projects() if target in (p.name, p.path.name)]
    return matches[0] if len(matches) == 1 else None


def show_list():
    projects = all_projects()
    if not projects:
        ui.info("Aucun projet trouvé. Crée le premier avec : felcloud new")
        ui.hint(f"Les projets sont rangés dans {config.projects_dir()}")
        return 0
    table = Table(title="Mes projets felcloud", title_justify="left")
    for col in ("Projet", "Outil", "Cloud", "État", "Dossier"):
        table.add_column(col)
    for p in projects:
        count, vms = p.summary()
        state = f"[green]déployé[/] ({vms} VM, {count} ressources)" if count else "[dim]non déployé[/]"
        folder = str(p.path).replace(str(Path.home()), "~", 1)
        if is_temporary(p.path):
            folder += " [yellow](temporaire !)[/]"
        table.add_row(f"[bold]{p.name}[/]", p.answers.get("tool", "?"), p.answers.get("cloud", "?"),
                      state, folder)
    ui.console.print(table)
    for path in missing_known_projects():
        ui.warn(f"Projet disparu : {path} (dossier supprimé). Ses ressources sont peut-être "
                "encore sur le cloud.")
    ui.hint("Voir un projet : cd <dossier> puis terraform output (ou pulumi stack output)    "
            "Supprimer : felcloud destroy <projet>")
    return 0


def destroy(target):
    project = find(target) if target else None
    if target and not project:
        ui.err(f"Projet introuvable : {target}")
        ui.hint("Liste tes projets avec : felcloud projets")
        return 1
    if not project:
        projects = all_projects()
        if not projects:
            ui.info("Aucun projet à supprimer.")
            return 0
        project = ui.select("Quel projet supprimer ?",
                            [ui.Choice(f"{p.name}   ({p.path})", value=p) for p in projects])

    resources = project.state()
    ui.title(f"Supprimer le projet {project.name}", str(project.path))
    if resources:
        ui.warn(f"{len(resources)} ressources vont être supprimées DÉFINITIVEMENT du cloud "
                f"« {project.answers.get('cloud')} » (machines, disques et leurs données compris).")
        kinds = sorted({r["type"].replace("openstack_", "").replace("openstack:", "") for r in resources})
        ui.hint(f"Types : {', '.join(kinds)}")
    else:
        ui.info("Rien n'est déployé sur le cloud pour ce projet.")
    if not ui.confirm(f"Confirmer la suppression de « {project.name} » ?", default=False):
        return 1

    if resources:
        from felcloud import runner
        tool = runner.tool_of(project.path)
        if not doctor.find_tool(tool):
            ui.err(f"{tool} n'est pas installé : felcloud install {tool}")
            return 1
        ips = runner.project_ips(runner.project_outputs(project.path))
        restore_key = _ensure_public_key(project)
        try:
            ok = runner.destroy(project.path)
            if not ok:
                ui.warn("Échec, probablement une coupure passagère de l'API : nouvel essai...")
                ok = runner.destroy(project.path)
        finally:
            if restore_key:
                restore_key.unlink(missing_ok=True)
        if not ok:
            ui.err("La suppression a échoué. Le projet est conservé : relance « felcloud destroy "
                   f"{project.name} » plus tard.")
            return 1
        ui.ok("Ressources supprimées du cloud.")
        runner.forget_host_keys(ips)

    if ui.confirm(f"Supprimer aussi le dossier {project.path} ?", default=True):
        shutil.rmtree(project.path)
        config.forget_project(project.path)
        ui.ok("Dossier supprimé.")
    kp = project.answers.get("keypair") or {}
    if kp.get("mode") == "generate":
        private = Path(kp["private_key_path"]).expanduser()
        if private.exists() and ui.confirm(f"Supprimer la clé SSH du projet ({private}) ?", default=True):
            private.unlink(missing_ok=True)
            Path(str(private) + ".pub").unlink(missing_ok=True)
            ui.ok("Clé SSH supprimée.")
    return 0


def _ensure_public_key(project):
    """Terraform relit la clé publique même pour détruire : si elle a été effacée, on en
    crée une provisoire au même chemin, supprimée juste après."""
    kp = project.answers.get("keypair") or {}
    if kp.get("mode") not in ("generate", "file"):
        return None
    pub = Path(kp["public_key_path"]).expanduser()
    if pub.exists():
        return None
    ui.warn(f"La clé {pub} a été supprimée : création d'une clé provisoire pour pouvoir détruire.")
    tmp_private = pub.with_name(pub.stem + ".felcloud-provisoire")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(tmp_private)], check=True)
    Path(str(tmp_private) + ".pub").rename(pub)
    tmp_private.unlink(missing_ok=True)
    return pub
