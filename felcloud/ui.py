"""Affichage et questions interactives (menus aux flèches)."""

import questionary
from questionary import Choice, Separator, Style
from rich.console import Console
from rich.panel import Panel

console = Console()

STYLE = Style([
    ("qmark", "fg:#2e86de bold"),
    ("question", "bold"),
    ("pointer", "fg:#2e86de bold"),
    ("highlighted", "fg:#2e86de bold"),
    ("selected", "fg:#27ae60"),
    ("answer", "fg:#27ae60 bold"),
    ("instruction", "fg:#7f8c8d italic"),
])

NAV_HINT = "(flèches pour choisir, Entrée pour valider)"
CHECK_HINT = "(flèches pour naviguer, Espace pour cocher, Entrée pour valider)"


class Abort(Exception):
    """L'utilisateur a quitté avec Ctrl+C."""


def _ask(question):
    answer = question.ask()
    if answer is None:
        raise Abort
    return answer


def select(message, choices, default=None):
    return _ask(questionary.select(
        message, choices=choices, default=default, style=STYLE, instruction=NAV_HINT,
    ))


def checkbox(message, choices, validate=None):
    return _ask(questionary.checkbox(
        message, choices=choices, style=STYLE, instruction=CHECK_HINT,
        validate=validate or (lambda _: True),
    ))


def confirm(message, default=True):
    return _ask(questionary.confirm(message, default=default, style=STYLE))


def text(message, default="", validate=None):
    return _ask(questionary.text(
        message, default=default, style=STYLE, validate=validate or (lambda _: True),
    ))


def password(message, validate=None):
    return _ask(questionary.password(message, style=STYLE, validate=validate or (lambda _: True)))


def path(message, default="", only_directories=False, validate=None):
    return _ask(questionary.path(message, default=default, only_directories=only_directories,
                                 validate=validate, style=STYLE))


def title(text_, subtitle=None):
    body = f"[bold]{text_}[/]"
    if subtitle:
        body += f"\n[dim]{subtitle}[/]"
    console.print()
    console.print(Panel(body, border_style="#2e86de", expand=False, padding=(0, 2)))


def section(text_):
    console.print(f"\n[bold #2e86de]── {text_} ──[/]")


def ok(msg):
    console.print(f"[green]✓[/] {msg}")


def warn(msg):
    console.print(f"[yellow]![/] {msg}")


def err(msg):
    console.print(f"[red]✗[/] {msg}")


def info(msg):
    console.print(f"[cyan]›[/] {msg}")


def hint(msg):
    console.print(f"  [dim]{msg}[/]")


__all__ = [
    "Abort", "Choice", "Panel", "Separator", "console", "select", "checkbox", "confirm", "text",
    "password", "path", "title", "section", "ok", "warn", "err", "info", "hint",
]
