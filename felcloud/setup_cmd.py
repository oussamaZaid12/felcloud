"""`felcloud setup` : installer et vérifier ses identifiants."""

import os
import platform
import shutil
import subprocess
from pathlib import Path

from rich.table import Table

from felcloud import cloud, config, credentials, projects, ui

GUIDE = f"""
[bold]Obtenir tes identifiants FelCloud (une seule fois)[/]

  1. Connecte-toi à la console FelCloud ([bold]Skyline[/]).
  2. Ouvre le menu, puis [bold]User Center → Application Credentials[/].
  3. Crée un identifiant : donne-lui un nom, laisse le reste par défaut.
  4. Skyline affiche alors un [bold]ID[/] et un [bold]secret[/].
     [yellow]Le secret n'est affiché qu'une seule fois : copie-le tout de suite.[/]

[bold]Ensuite, au choix[/]

  • Télécharge le fichier [bold]clouds.yaml[/] proposé par Skyline, puis relance
    [bold]felcloud setup[/] : il le trouve dans tes Téléchargements et le range
    à sa place, [bold]{credentials.CLOUDS_FILE}[/]
  • Ou relance [bold]felcloud setup[/], choisis « Saisir mon ID et mon secret »,
    et colle les deux valeurs.
  • Ou écris toi-même l'entrée dans [bold]{credentials.CLOUDS_FILE}[/] :

      clouds:
        mon-projet:
          auth:
            auth_url: {credentials.FELCLOUD_AUTH_URL}
            application_credential_id: "TON_ID"
            application_credential_secret: "TON_SECRET"
          region_name: {credentials.FELCLOUD_REGION}
          interface: public
          identity_api_version: 3
          auth_type: v3applicationcredential

    puis protège le fichier : [bold]chmod 600 {credentials.CLOUDS_FILE}[/]
"""


def show_installed():
    clouds = credentials.installed_clouds()
    if not clouds:
        ui.info(f"Aucun cloud configuré pour l'instant ({credentials.CLOUDS_FILE} n'existe pas).")
        return clouds
    default = config.default_cloud()
    table = Table(title=f"Clouds configurés dans {credentials.CLOUDS_FILE}", title_justify="left")
    for col in ("Nom", "Authentification", "Adresse", "Région"):
        table.add_column(col)
    for name, entry in clouds.items():
        d = credentials.describe(entry)
        label = f"[bold]{name}[/] [green](défaut)[/]" if name == default else name
        table.add_row(label, d["type"], d["endpoint"], d["region"])
    ui.console.print(table)
    return clouds


def run_check(name, offer_default=True):
    with ui.console.status(f"Connexion au cloud [bold]{name}[/]..."):
        result = cloud.check(name)
    if not result.ok:
        ui.err(f"Échec de connexion à [bold]{name}[/]")
        ui.hint(result.error)
        return False

    ui.ok(f"Connexion réussie à [bold]{name}[/]")
    ui.hint(f"Projet : {result.project_id}   Région : {result.region or '—'}")
    if result.usage:
        table = Table(title="Utilisation du projet", title_justify="left")
        table.add_column("Ressource")
        table.add_column("Utilisé", justify="right")
        table.add_column("Maximum", justify="right")
        for label, (used, maximum) in result.usage.items():
            table.add_row(label, str(used), "illimité" if maximum in (-1, None) else str(maximum))
        ui.console.print(table)

    if offer_default and config.default_cloud() != name:
        if ui.confirm(f"Utiliser « {name} » comme cloud par défaut ?", default=True):
            config.set_default_cloud(name)
            ui.ok("Cloud par défaut enregistré.")
    return True


def _open_folder(folder):
    """Ouvre le dossier dans l'explorateur de fichiers, si la machine en a un."""
    opener = "open" if platform.system() == "Darwin" else "xdg-open"
    if not shutil.which(opener) or (opener == "xdg-open" and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))):
        return False
    subprocess.Popen([opener, str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def show_location():
    """Indique où doit se trouver clouds.yaml, et crée le dossier s'il manque."""
    credentials.CLOUDS_DIR.mkdir(parents=True, exist_ok=True)
    ui.console.print(ui.Panel(
        "Tous les outils (felcloud, Terraform, Pulumi, openstack) lisent tes identifiants ici :\n\n"
        f"  [bold #2e86de]{credentials.CLOUDS_FILE}[/]\n\n"
        "[dim]Le dossier .config est caché : dans l'explorateur de fichiers, Ctrl+H\n"
        "(Linux) ou Cmd+Maj+. (macOS) affiche les dossiers cachés.[/]",
        title="Emplacement de clouds.yaml", title_align="left", border_style="#2e86de", expand=False))


def _drop_file_yourself():
    """L'utilisateur dépose lui-même le fichier dans le dossier, qu'on lui ouvre."""
    folder = credentials.CLOUDS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    if _open_folder(folder):
        ui.ok(f"Dossier ouvert : {folder}")
    ui.info(f"Copie ton fichier [bold]clouds.yaml[/] dans [bold]{folder}[/]")
    ui.hint(f"En ligne de commande : mv ~/Downloads/clouds.yaml {folder}/")
    while not credentials.CLOUDS_FILE.exists():
        if not ui.confirm("C'est fait ?", default=True):
            return None
        if not credentials.CLOUDS_FILE.exists():
            ui.warn(f"Toujours rien dans {credentials.CLOUDS_FILE} : vérifie que le fichier "
                    "s'appelle exactement clouds.yaml.")
    try:
        names = list(credentials.installed_clouds())
    except credentials.CloudsFileError as exc:
        ui.err(str(exc))
        return None
    credentials.protect()
    ui.ok(f"Fichier trouvé ({', '.join(names)}) et protégé : lisible par toi seul (chmod 600)")
    return names


def _pick_file():
    found = credentials.find_downloaded_files()
    choices = [ui.Choice(f"{p.name}   [{p.parent}]", value=str(p)) for p in found[:8]]
    if not credentials.CLOUDS_FILE.exists():
        choices.append(ui.Choice("Je le copie moi-même dans le bon dossier", value="drop"))
    choices.append(ui.Choice("Indiquer où il se trouve...", value=""))
    if found:
        message = "Quel fichier ranger à sa place ? (le plus récent est en haut)"
    else:
        ui.info("Aucun clouds.yaml dans tes Téléchargements.")
        message = "Que faire ?"
    picked = ui.select(message, choices)
    return picked or ui.path("Chemin du fichier clouds.yaml :", default=str(Path.home()) + "/")


def _resolve_conflict(name):
    suggestion = credentials.free_name(name)
    action = ui.select(
        f"Un cloud nommé « {name} » existe déjà avec d'autres identifiants. Que faire ?",
        [
            ui.Choice(f"Garder les deux : enregistrer le nouveau sous « {suggestion} »", value="rename"),
            ui.Choice("Choisir un autre nom", value="custom"),
            ui.Choice(f"Remplacer l'ancien « {name} »", value="replace"),
            ui.Choice("Ignorer ce cloud", value="skip"),
        ],
    )
    if action == "rename":
        return suggestion
    if action == "custom":
        return ui.text("Nouveau nom :", validate=_valid_name)
    if action == "replace":
        return name
    return None


def _valid_name(value):
    if not value.strip():
        return "Le nom ne peut pas être vide."
    if any(c.isspace() for c in value):
        return "Pas d'espace dans le nom (utilise - ou _)."
    if value in credentials.installed_clouds():
        return "Ce nom est déjà utilisé."
    return True


def import_file(path, resolve_conflict, rename=None):
    try:
        doc = credentials.read_document(path)
    except credentials.CloudsFileError as exc:
        ui.err(str(exc))
        return []

    if rename:
        if len(doc["clouds"]) != 1:
            ui.err("--as ne fonctionne qu'avec un fichier contenant un seul cloud.")
            return []
        doc = {"clouds": {rename: next(iter(doc["clouds"].values()))}}

    for name, entry in doc["clouds"].items():
        problem = credentials.missing_secret(entry)
        if problem:
            ui.err(f"« {name} » est incomplet : {problem}.")
            return []

    added, unchanged, backup = credentials.import_clouds(doc, resolve_conflict)
    for name in unchanged:
        ui.info(f"« {name} » est déjà installé à l'identique.")
    if backup:
        ui.ok(f"Ancienne version sauvegardée : {backup}")
    for name in added:
        ui.ok(f"« {name} » ajouté dans {credentials.CLOUDS_FILE}")
    if added:
        ui.ok("Fichier protégé : lisible par toi seul (chmod 600)")
    source = Path(path).expanduser()
    if (added or unchanged) and source.resolve() != credentials.CLOUDS_FILE.resolve():
        if ui.confirm(f"Supprimer la copie {source} ? Elle contient ton secret en clair.",
                      default=True):
            source.unlink()
            ui.ok("Copie supprimée.")
    return added or unchanged


def _required(value):
    return True if value.strip() else "Ce champ est obligatoire."


def manual_entry():
    """Crée une entrée clouds.yaml à partir de l'ID et du secret affichés par Skyline."""
    ui.section("Nouvel identifiant")
    ui.hint("Appuie sur Entrée pour garder les valeurs proposées par défaut.")
    name = ui.text("Nom court pour ce cloud :", default=credentials.free_name("felcloud"),
                   validate=_valid_name)
    auth_url = ui.text("Adresse d'authentification :", default=credentials.FELCLOUD_AUTH_URL,
                       validate=_required)
    region = ui.text("Région :", default=credentials.FELCLOUD_REGION, validate=_required)
    credential_id = ui.text("ID de l'application credential :", validate=_required).strip()
    secret = ui.password("Secret (il ne s'affiche pas pendant la saisie) :", validate=_required).strip()

    entry = credentials.application_credential_entry(auth_url.strip(), region.strip(),
                                                     credential_id, secret)
    added, _, backup = credentials.import_clouds({"clouds": {name: entry}}, _resolve_conflict)
    if backup:
        ui.ok(f"Ancienne version sauvegardée : {backup}")
    if added:
        ui.ok(f"« {name} » ajouté dans {credentials.CLOUDS_FILE} (chmod 600)")
    return added[0] if added else None


def _valid_projects_dir(value):
    path = Path(value.strip() or ".").expanduser()
    if not value.strip():
        return "Indique un dossier."
    if projects.is_temporary(path):
        return "Ce dossier est temporaire (effacé au redémarrage) : choisis-en un autre."
    if path.exists() and not path.is_dir():
        return "C'est un fichier, pas un dossier."
    existing = next((p for p in [path, *path.parents] if p.exists()), None)
    if existing is None or not os.access(existing, os.W_OK):
        return "Tu n'as pas le droit d'écrire dans ce dossier."
    return True


def ask_projects_dir():
    """Choix du dossier où seront créés tous les projets felcloud."""
    ui.section("Dossier de tes projets")
    ui.hint("Chaque projet felcloud y aura son propre sous-dossier. Garde-le : il contient "
            "l'état de tes projets, indispensable pour les modifier ou les supprimer.")
    current = str(config.projects_dir()).replace(str(Path.home()), "~", 1)
    value = ui.path("Dossier des projets :", default=current, only_directories=True,
                    validate=_valid_projects_dir)
    folder = config.set_projects_dir(value.strip())
    ui.ok(f"Tes projets seront créés dans [bold]{folder}[/]")
    return folder


def interactive():
    ui.title("Configuration de felcloud",
             "1. tes identifiants (clouds.yaml)   2. le dossier de tes projets")
    try:
        clouds = show_installed()
    except credentials.CloudsFileError as exc:
        ui.err(f"Ton clouds.yaml actuel est illisible : {exc}")
        return
    if not clouds:
        show_location()
    if clouds and not credentials.is_protected():
        ui.warn("Ton clouds.yaml est lisible par d'autres utilisateurs de la machine.")
        if ui.confirm("Le protéger maintenant (chmod 600) ?"):
            credentials.protect()
            ui.ok("Fichier protégé.")

    choices = []
    if clouds:
        choices.append(ui.Choice("Tester un cloud déjà configuré et le choisir par défaut", value="check"))
    choices += [
        ui.Choice("J'ai téléchargé clouds.yaml depuis Skyline : le ranger à sa place", value="import"),
        ui.Choice("Saisir mon ID et mon secret (copiés depuis Skyline)", value="manual"),
        ui.Choice("Comment obtenir mes identifiants ?", value="guide"),
    ]
    if config.projects_dir_chosen():
        choices.append(ui.Choice(f"Changer le dossier de mes projets (actuel : {config.projects_dir()})",
                                 value="folder"))
    choices.append(ui.Choice("Retour", value="back"))
    action = ui.select("Que veux-tu faire ?", choices)

    if action == "guide":
        ui.console.print(GUIDE)
    elif action == "manual":
        name = manual_entry()
        if name:
            run_check(name)
    elif action == "import":
        picked = _pick_file()
        names = _drop_file_yourself() if picked == "drop" else import_file(picked, _resolve_conflict)
        if names:
            target = names[0] if len(names) == 1 else ui.select("Quel cloud tester ?", names)
            run_check(target)
    elif action == "check":
        default = config.default_cloud()
        target = ui.select("Quel cloud tester ?", list(clouds),
                           default=default if default in clouds else None)
        run_check(target)
    elif action == "folder":
        ask_projects_dir()
        return

    if action != "back" and not config.projects_dir_chosen():
        ask_projects_dir()


def non_interactive(import_path=None, as_name=None, check_name=None, projects_dir=None):
    """Variante sans menus, pour les scripts et les tests."""
    if projects_dir:
        problem = _valid_projects_dir(projects_dir)
        if problem is not True:
            ui.err(problem)
            return 1
        ui.ok(f"Tes projets seront créés dans {config.set_projects_dir(projects_dir)}")
        if not (import_path or check_name):
            return 0
    if import_path:
        def resolve(name):
            ui.err(f"« {name} » existe déjà avec d'autres identifiants : choisis un autre nom avec --as.")
            return None

        names = import_file(import_path, resolve, rename=as_name)
        if not names:
            return 1
        check_name = check_name or names[0]
    if check_name:
        return 0 if run_check(check_name, offer_default=False) else 1
    show_installed()
    return 0
