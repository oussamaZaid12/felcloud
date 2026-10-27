#!/usr/bin/env bash
# Installe la commande `felcloud` pour l'utilisateur courant, sans sudo.
#
#   ./install.sh              installation normale
#   ./install.sh --dev        installation modifiable (le code du dépôt est utilisé en direct)
#   ./install.sh --uninstall  désinstallation (clouds.yaml et projets ne sont pas touchés)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${FELCLOUD_HOME:-$HOME/.local/share/felcloud}"
BIN_DIR="$HOME/.local/bin"
MODE="install"

green() { printf '\033[32m✓\033[0m %s\n' "$*"; }
yellow() { printf '\033[33m!\033[0m %s\n' "$*"; }
die() { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --dev) MODE="dev" ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Option inconnue : $arg (voir ./install.sh --help)" ;;
  esac
done

if [[ "$MODE" == "uninstall" ]]; then
  rm -rf "$APP_DIR"
  rm -f "$BIN_DIR/felcloud"
  green "felcloud désinstallé."
  echo "  Conservés : ~/.config/openstack/clouds.yaml, ~/.config/felcloud/ et tes projets."
  exit 0
fi

[[ "$(uname -s)" == "Linux" ]] || die "felcloud fonctionne uniquement sous Linux."

command -v python3 >/dev/null 2>&1 || die "Python 3 est introuvable.
  Ubuntu/Debian : sudo apt install python3 python3-venv
  Fedora        : sudo dnf install python3
  Arch          : sudo pacman -S python"

python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
  || die "Python 3.10 minimum est requis (trouvé : $(python3 --version 2>&1))."

python3 -c 'import venv, ensurepip' 2>/dev/null \
  || die "Le module venv de Python est absent.
  Ubuntu/Debian : sudo apt install python3-venv"

green "Python $(python3 -c 'import platform; print(platform.python_version())')"

echo "Création de l'environnement dans $APP_DIR ..."
mkdir -p "$APP_DIR"
python3 -m venv --clear "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip

echo "Installation de felcloud et de ses dépendances (une minute environ) ..."
if [[ "$MODE" == "dev" ]]; then
  "$APP_DIR/venv/bin/pip" install --quiet --editable "$REPO_DIR"
else
  "$APP_DIR/venv/bin/pip" install --quiet "$REPO_DIR"
fi
green "felcloud installé"

mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/venv/bin/felcloud" "$BIN_DIR/felcloud"
green "Commande disponible : $BIN_DIR/felcloud"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    yellow "$BIN_DIR n'est pas dans ton PATH. Ajoute-le une fois pour toutes :"
    case "$(basename "${SHELL:-bash}")" in
      fish) echo "    fish_add_path ~/.local/bin" ;;
      zsh)  echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc" ;;
      *)    echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc" ;;
    esac
    ;;
esac

echo
echo "Étapes suivantes :"
echo "    felcloud doctor     vérifier que la machine est prête"
echo "    felcloud setup      installer tes identifiants"
