"""`felcloud setup` : installer et vérifier ses identifiants."""

from pathlib import Path

from rich.table import Table

from felcloud import cloud, config, credentials, ui

GUIDE = f"""
[bold]Obtenir tes identifiants FelCloud (une seule fois)[/]

  1. Connecte-toi à la console FelCloud ([bold]Skyline[/]).
  2. Ouvre le menu, puis [bold]User Center → Application Credentials[/].
  3. Crée un identifiant : donne-lui un nom, laisse le reste par défaut.
  4. Skyline affiche alors un [bold]ID[/] et un [bold]secret[/].
     [yellow]Le secret n'est affiché qu'une seule fois : copie-le tout de suite.[/]

[bold]Ensuite, deux possibilités[/]

  • Le plus simple : relance [bold]felcloud setup[/], choisis
    « Saisir mon ID et mon secret », et colle les deux valeurs.
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


def _pick_file():
    found = credentials.find_downloaded_files()
    if found:
        choices = [ui.Choice(f"{p.name}   [{p.parent}]", value=str(p)) for p in found[:8]]
        choices.append(ui.Choice("Autre emplacement...", value=""))
        picked = ui.select("Quel fichier importer ? (le plus récent est en haut)", choices)
        if picked:
            return picked
    return ui.path("Chemin du fichier clouds.yaml :", default=str(Path.home()) + "/")


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
        ui.hint(f"Pense à supprimer la copie {path}, qui contient ton secret en clair.")
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


def interactive():
    ui.title("Configuration des identifiants",
             f"Tous les outils lisent {credentials.CLOUDS_FILE}")
    try:
        clouds = show_installed()
    except credentials.CloudsFileError as exc:
        ui.err(f"Ton clouds.yaml actuel est illisible : {exc}")
        return
    if clouds and not credentials.is_protected():
        ui.warn("Ton clouds.yaml est lisible par d'autres utilisateurs de la machine.")
        if ui.confirm("Le protéger maintenant (chmod 600) ?"):
            credentials.protect()
            ui.ok("Fichier protégé.")

    choices = []
    if clouds:
        choices.append(ui.Choice("Tester un cloud déjà configuré et le choisir par défaut", value="check"))
    choices += [
        ui.Choice("Saisir mon ID et mon secret (copiés depuis Skyline)", value="manual"),
        ui.Choice("Importer un fichier clouds.yaml", value="import"),
        ui.Choice("Comment obtenir mes identifiants ?", value="guide"),
        ui.Choice("Retour", value="back"),
    ]
    action = ui.select("Que veux-tu faire ?", choices)

    if action == "guide":
        ui.console.print(GUIDE)
    elif action == "manual":
        name = manual_entry()
        if name:
            run_check(name)
    elif action == "import":
        names = import_file(_pick_file(), _resolve_conflict)
        if names:
            target = names[0] if len(names) == 1 else ui.select("Quel cloud tester ?", names)
            run_check(target)
    elif action == "check":
        default = config.default_cloud()
        target = ui.select("Quel cloud tester ?", list(clouds),
                           default=default if default in clouds else None)
        run_check(target)


def non_interactive(import_path=None, as_name=None, check_name=None):
    """Variante sans menus, pour les scripts et les tests."""
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
