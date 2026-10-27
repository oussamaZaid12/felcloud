#!/usr/bin/env bash
# Installe la commande `felcloud` pour l'utilisateur courant, sans sudo (Linux et macOS).
#
#   curl -fsSL https://raw.githubusercontent.com/oussamaZaid12/felcloud/main/install.sh | bash
#
#   ./install.sh              installation depuis ce dossier
#   ./install.sh --dev        installation modifiable (le code du dépôt est utilisé en direct)
#   ./install.sh --uninstall  désinstallation (clouds.yaml et projets ne sont pas touchés)

set -euo pipefail

REPO_URL="https://github.com/oussamaZaid12/felcloud"
APP_DIR="${FELCLOUD_HOME:-$HOME/.local/share/felcloud}"
BIN_DIR="$HOME/.local/bin"
MARK="# ajouté par felcloud"
MODE="install"

green() { printf '\033[32m✓\033[0m %s\n' "$*"; }
yellow() { printf '\033[33m!\033[0m %s\n' "$*"; }
die() { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --dev) MODE="dev" ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Option inconnue : $arg (voir ./install.sh --help)" ;;
  esac
done

# Lancé depuis un clone du dépôt, ou téléchargé par curl (aucun fichier à côté) ?
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" && pwd)"
if grep -qs '^name = "felcloud"' "$SCRIPT_DIR/pyproject.toml"; then
  SOURCE="$SCRIPT_DIR"
else
  SOURCE="${FELCLOUD_SOURCE:-$REPO_URL/archive/refs/heads/main.tar.gz}"
  [[ "$MODE" == "dev" ]] && die "--dev s'utilise depuis un clone du dépôt : git clone $REPO_URL"
fi

# Fichiers de démarrage des shells dans lesquels on ajoute ~/.local/bin au PATH.
rc_files() {
  echo "$HOME/.bashrc"
  [[ "$(uname -s)" == "Darwin" ]] && echo "$HOME/.bash_profile"
  echo "$HOME/.zshrc"
}
FISH_CONF="$HOME/.config/fish/conf.d/felcloud.fish"

if [[ "$MODE" == "uninstall" ]]; then
  rm -rf "$APP_DIR"
  rm -f "$BIN_DIR/felcloud" "$FISH_CONF"
  for rc in $(rc_files); do
    if [[ -f "$rc" ]] && grep -q "$MARK" "$rc"; then
      grep -v "$MARK" "$rc" > "$rc.felcloud-tmp" && mv "$rc.felcloud-tmp" "$rc"
    fi
  done
  green "felcloud désinstallé."
  echo "  Conservés : ~/.config/openstack/clouds.yaml, ~/.config/felcloud/ et tes projets."
  exit 0
fi

case "$(uname -s)" in
  Linux|Darwin) ;;
  *) die "Ce script est prévu pour Linux et macOS." ;;
esac

# --- Python ------------------------------------------------------------------
# On utilise le Python de la machine s'il convient (3.10 ou plus, avec venv).
# Sinon, uv (un petit programme autonome) télécharge un Python privé pour felcloud :
# rien à installer à la main, et rien ne change pour le reste du système.
system_python_ok() {
  command -v python3 >/dev/null 2>&1 \
    && python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null \
    && python3 -c 'import venv, ensurepip' 2>/dev/null
}

mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/venv"
if system_python_ok; then
  green "Python $(python3 -c 'import platform; print(platform.python_version())')"
  python3 -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/python" -m pip install --quiet --upgrade pip
  PIP=("$APP_DIR/venv/bin/python" -m pip install --quiet)
else
  yellow "Python 3.10+ absent ou incomplet : felcloud utilisera son propre Python."
  command -v curl >/dev/null 2>&1 || die "curl est nécessaire (Ubuntu/Debian : sudo apt install curl)."
  echo "Téléchargement de uv (gestionnaire Python autonome) ..."
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_UNMANAGED_INSTALL="$APP_DIR/uv" INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null \
    || die "Échec du téléchargement de uv. Installe plutôt Python 3.10+ :
  Ubuntu/Debian : sudo apt install python3 python3-venv
  macOS         : https://www.python.org/downloads/"
  UV="$APP_DIR/uv/uv"
  export UV_PYTHON_INSTALL_DIR="$APP_DIR/python"
  echo "Téléchargement de Python 3.12 ..."
  "$UV" venv --quiet --python 3.12 "$APP_DIR/venv"
  green "Python $("$APP_DIR/venv/bin/python" -c 'import platform; print(platform.python_version())')"
  PIP=("$UV" pip install --quiet --python "$APP_DIR/venv/bin/python")
fi

# --- felcloud ----------------------------------------------------------------
echo "Installation de felcloud et de ses dépendances (une minute environ) ..."
if [[ "$MODE" == "dev" ]]; then
  "${PIP[@]}" --editable "$SOURCE"
else
  "${PIP[@]}" "$SOURCE"
fi
green "felcloud installé"

mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/venv/bin/felcloud" "$BIN_DIR/felcloud"
green "Commande disponible : $BIN_DIR/felcloud"

# --- PATH --------------------------------------------------------------------
# ~/.local/bin accueille aussi terraform, pulumi, go et node installés par felcloud.
for rc in $(rc_files); do
  [[ "$rc" == "$HOME/.bashrc" || -f "$rc" || "$(uname -s)" == "Darwin" ]] || continue
  [[ -f "$rc" ]] && grep -q "$MARK" "$rc" && continue
  printf '\nexport PATH="$HOME/.local/bin:$PATH"  %s\n' "$MARK" >> "$rc"
done
if command -v fish >/dev/null 2>&1; then
  mkdir -p "$(dirname "$FISH_CONF")"
  echo "fish_add_path -g ~/.local/bin  $MARK" > "$FISH_CONF"
fi
case ":$PATH:" in
  *":$BIN_DIR:"*) NEW_TERMINAL=0 ;;
  *) NEW_TERMINAL=1 ;;
esac

echo
echo "Étapes suivantes :"
echo "    felcloud setup      tes identifiants (clouds.yaml) et le dossier de tes projets"
echo "    felcloud new        créer ton premier projet"
if [[ "$NEW_TERMINAL" == 1 ]]; then
  yellow "Ouvre un nouveau terminal pour que la commande felcloud soit reconnue."
fi

# Enchaîne directement sur la configuration, si un terminal est disponible
# (avec curl | bash, le clavier est lu sur /dev/tty).
if [[ -z "${FELCLOUD_NO_SETUP:-}" ]] && { exec 3</dev/tty; } 2>/dev/null; then
  exec 3<&-
  echo
  "$BIN_DIR/felcloud" setup </dev/tty || true
fi
