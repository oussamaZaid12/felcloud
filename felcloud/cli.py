"""Point d'entrée de la commande `felcloud`."""

import argparse
import os
import sys
from pathlib import Path

import yaml

from felcloud import __version__, config, credentials, doctor, installer, projects, setup_cmd, ui

EPILOG = """exemples :
  felcloud                     menu principal
  felcloud setup               installer ses identifiants (clouds.yaml)
  felcloud new                 créer un projet (rangé dans ~/felcloud-projets/)
  felcloud projets             lister mes projets
  felcloud test PROJET         vérifier que les machines répondent en SSH
  felcloud destroy PROJET      tout supprimer : cloud, dossier, clé
  felcloud doctor              vérifier que la machine est prête
"""


def main_menu():
    ui.title(f"felcloud {__version__}", "Créer ton infrastructure OpenStack pas à pas")
    while True:
        choice = ui.select("Que veux-tu faire ?", [
            ui.Choice("Créer un nouveau projet", value="new"),
            ui.Choice("Voir mes projets", value="list"),
            ui.Choice("Supprimer un projet", value="destroy"),
            ui.Choice("Configurer mes identifiants (clouds.yaml)", value="setup"),
            ui.Choice("Vérifier que ma machine est prête", value="doctor"),
            ui.Choice("Quitter", value="quit"),
        ])
        if choice == "quit":
            return 0
        try:
            if choice == "new":
                return cmd_new(argparse.Namespace(answers=None, output=None, no_preview=False))
            if choice == "list":
                projects.show_list()
            elif choice == "destroy":
                projects.destroy(None)
            elif choice == "setup":
                setup_cmd.interactive()
            elif choice == "doctor":
                doctor.run()
        except ui.Abort as exc:
            if str(exc):
                ui.err(str(exc))


def cmd_new(args):
    from felcloud import generator, runner, wizard

    if args.answers:
        answers = yaml.safe_load(Path(args.answers).read_text())
        interactive = False
    else:
        answers = wizard.run()
        interactive = True
    dest = Path(args.output).expanduser() if args.output else config.PROJECTS_DIR / answers["project"]
    if projects.is_temporary(dest):
        ui.warn(f"{dest} est un dossier TEMPORAIRE, effacé au redémarrage. Avec lui disparaîtrait "
                "l'état du projet, et l'outil ne saurait plus quoi supprimer sur le cloud.")
        if interactive and not ui.confirm("Créer le projet ici quand même ?", default=False):
            dest = config.PROJECTS_DIR / answers["project"]

    try:
        written = generator.generate(answers, dest)
    except FileExistsError as exc:
        ui.err(str(exc))
        return 1
    config.remember_project(dest)
    key = generator.ensure_ssh_key(answers)

    ui.console.print()
    ui.ok(f"Projet créé dans [bold]{dest}/[/]")
    for name in written:
        ui.hint(f"  {name}")
    if key:
        ui.ok(f"Nouvelle clé SSH créée : {key} (et {key}.pub)")

    tf = answers["tool"] == "terraform"
    created = False
    if interactive and not args.no_preview and ui.confirm(
            "Lancer l'aperçu maintenant (" + ("terraform init + plan" if tf else "pulumi preview")
            + ", rien n'est créé) ?", default=True):
        if not runner.preview(dest):
            return 1
        if ui.confirm("Créer réellement cette infrastructure maintenant ("
                      + ("terraform apply" if tf else "pulumi up") + ") ?", default=False):
            created = runner.apply(dest)
            if not created:
                return 1
            runner.check_connectivity(dest)

    _next_steps(dest, created, tf)
    return 0


def _passphrase_line():
    shell = Path(os.environ.get("SHELL", "bash")).name
    return 'set -x PULUMI_CONFIG_PASSPHRASE ""' if shell == "fish" else 'export PULUMI_CONFIG_PASSPHRASE=""'


def _next_steps(dest, created, tf=True):
    """Rappel affiché en tout dernier, pour qu'il reste visible à l'écran."""
    folder = dest.resolve()
    name = dest.name
    lines = ["[bold]Va dans le dossier du projet[/] (toutes les commandes s'y lancent) :",
             f"  [bold #2e86de]cd {folder}[/]", ""]
    if tf:
        if created:
            lines += ["  terraform output        revoir les adresses IP et les commandes SSH"]
        else:
            lines += ["  terraform init          télécharger le provider (une fois)",
                      "  terraform plan          voir ce qui va être créé",
                      "  terraform apply         créer pour de vrai"]
    else:
        lines += ["  Une fois par terminal (aucun secret dans ce projet) :",
                  f"  [bold]{_passphrase_line()}[/]", ""]
        if created:
            lines += ["  pulumi stack output     revoir les adresses IP et les commandes SSH"]
        else:
            if (dest / "go.mod").exists():
                lines += ["  go mod tidy             télécharger les bibliothèques Go (une fois)"]
            lines += ["  pulumi install          installer les bibliothèques (une fois)",
                      "  pulumi stack select --create dev   (une fois)",
                      "  pulumi preview          voir ce qui va être créé",
                      "  pulumi up               créer pour de vrai"]
    lines += ["",
              f"  felcloud test {name}       vérifier que les machines répondent",
              f"  felcloud destroy {name}    tout supprimer quand tu as fini",
              "", f"[dim]Tout est expliqué dans {folder}/README.md[/]"]
    ui.console.print()
    ui.console.print(ui.Panel("\n".join(lines), title="Étapes suivantes", title_align="left",
                              border_style="#2e86de", expand=False))


def cmd_test(args):
    from felcloud import runner

    project = projects.find(args.project) if args.project else projects.find(".")
    if not project:
        ui.err("Projet introuvable. Donne son nom (felcloud projets) ou lance la commande dans son dossier.")
        return 1
    if not project.state():
        ui.info(f"« {project.name} » n'est pas déployé : rien à tester.")
        return 0
    return 0 if runner.check_connectivity(project.path) else 1


def cmd_check(args):
    name = args.cloud or config.default_cloud()
    if not name:
        clouds = credentials.installed_clouds()
        if not clouds:
            ui.err("Aucun cloud configuré : lance « felcloud setup ».")
            return 1
        name = ui.select("Quel cloud tester ?", list(clouds))
    return 0 if setup_cmd.run_check(name, offer_default=False) else 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="felcloud",
        description="Assistant pour créer une infrastructure OpenStack avec Terraform ou Pulumi.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"felcloud {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMANDE")

    p_setup = sub.add_parser("setup", help="installer et vérifier ses identifiants")
    p_setup.add_argument("--import", dest="import_path", metavar="FICHIER",
                         help="importer ce clouds.yaml sans passer par les menus")
    p_setup.add_argument("--as", dest="as_name", metavar="NOM",
                         help="nom sous lequel enregistrer le cloud importé")

    p_check = sub.add_parser("check", help="tester la connexion à un cloud")
    p_check.add_argument("cloud", nargs="?", help="nom du cloud (défaut : cloud par défaut)")

    p_new = sub.add_parser("new", help="créer un nouveau projet avec l'assistant")
    p_new.add_argument("--answers", metavar="FICHIER",
                       help="regénérer à partir d'un felcloud.yaml existant, sans les questions")
    p_new.add_argument("--output", metavar="DOSSIER",
                       help="dossier de destination (défaut : ~/felcloud-projets/NOM)")
    p_new.add_argument("--no-preview", action="store_true", help="ne pas proposer l'aperçu à la fin")

    sub.add_parser("projets", aliases=["projects", "list"], help="lister mes projets")
    p_test = sub.add_parser("test", help="vérifier que les machines d'un projet répondent en SSH")
    p_test.add_argument("project", nargs="?", metavar="PROJET", help="nom ou dossier (défaut : dossier courant)")
    p_destroy = sub.add_parser("destroy", help="supprimer un projet : ressources du cloud, dossier, clé")
    p_destroy.add_argument("project", nargs="?", metavar="PROJET", help="nom ou dossier du projet")

    sub.add_parser("clouds", help="lister les clouds configurés")
    sub.add_parser("doctor", help="vérifier que la machine est prête")

    p_install = sub.add_parser("install", help="installer un outil manquant")
    p_install.add_argument("tool", choices=["terraform", "pulumi", "go", "node"])
    return parser


def dispatch(args):
    if args.command is None:
        return main_menu()
    if args.command == "setup":
        if args.import_path:
            return setup_cmd.non_interactive(import_path=args.import_path, as_name=args.as_name)
        setup_cmd.interactive()
        return 0
    if args.command == "check":
        return cmd_check(args)
    if args.command == "new":
        return cmd_new(args)
    if args.command in ("projets", "projects", "list"):
        return projects.show_list()
    if args.command == "test":
        return cmd_test(args)
    if args.command == "destroy":
        return projects.destroy(args.project)
    if args.command == "clouds":
        setup_cmd.show_installed()
        return 0
    if args.command == "doctor":
        return 1 if doctor.run() else 0
    if args.command == "install":
        return installer.INSTALLERS[args.tool]()
    return 1


def main():
    args = build_parser().parse_args()
    try:
        code = dispatch(args)
    except ui.Abort as exc:
        if str(exc):
            ui.err(str(exc))
        else:
            ui.console.print("\n[dim]Annulé.[/]")
        code = 130
    except credentials.CloudsFileError as exc:
        ui.err(str(exc))
        code = 1
    sys.exit(code)
