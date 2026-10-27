# felcloud

**Crée tes machines virtuelles sur FelCloud en répondant à quelques questions.**

Tu choisis avec les flèches du clavier ce que tu veux (réseau, machines, IP publique, disques).
felcloud écrit le code **Terraform** ou **Pulumi** (Python, JavaScript ou Go) à ta place, crée tout sur FelCloud,
vérifie que les machines répondent, puis supprime tout proprement quand tu as fini.

---

## 1. Installer (une seule fois)

Il te faut Linux, Python 3.10+ et Git.

```bash
git clone <URL-du-dépôt> FelcloudGuide
cd FelcloudGuide
./install.sh
```

Si `felcloud` n'est pas trouvé ensuite, lance `fish_add_path ~/.local/bin` (fish)
ou `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc` (bash), puis ouvre un nouveau terminal.

## 2. Ajouter tes identifiants (une seule fois)

**Dans Skyline** : Menu → **User Center** → **Application Credentials** → crée un identifiant.
Le secret n'est affiché qu'une seule fois : choisis tout de suite **l'une** des deux méthodes ci-dessous.

**Méthode A — télécharger le fichier `clouds.yaml`** proposé par Skyline, puis le mettre à sa place :

```bash
mkdir -p ~/.config/openstack
mv ~/Téléchargements/clouds.yaml ~/.config/openstack/clouds.yaml    # ou ~/Downloads/clouds.yaml
chmod 600 ~/.config/openstack/clouds.yaml                             # lisible par toi seul
felcloud setup      # choisis « Tester un cloud déjà configuré »
```

> ⚠️ Si tu as **déjà** un fichier `~/.config/openstack/clouds.yaml`, ne l'écrase pas avec `mv` :
> utilise plutôt `felcloud setup` → « Importer un fichier clouds.yaml », qui **ajoute** le nouveau cloud sans effacer les autres.

**Méthode B — copier l'ID et le secret** affichés par Skyline :

```bash
felcloud setup      # choisis « Saisir mon ID et mon secret » et colle-les
```

Dans les deux cas, felcloud teste la connexion. Réponds **Oui** à « Utiliser comme cloud par défaut », puis vérifie que tout est prêt :

```bash
felcloud doctor
```

Si `doctor` dit qu'il manque un outil, installe celui que tu veux utiliser (sans sudo) :

```bash
felcloud install terraform     # pour Terraform
felcloud install pulumi        # pour Pulumi
felcloud install node          # en plus, pour Pulumi en JavaScript
felcloud install go            # en plus, pour Pulumi en Go
```

## 3. Créer ton infrastructure

```bash
felcloud new
```

Réponds aux questions (**flèches** pour choisir, **Espace** pour cocher, **Entrée** pour valider).
En cas de doute, garde la réponse proposée. Les bons choix :

| Question | Réponse conseillée |
|---|---|
| Outil | Terraform, ou Pulumi en Python, JavaScript ou Go : même résultat |
| Réseau | Créer un nouveau réseau |
| Accès depuis Internet | Ajouter une VM bastion dédiée |
| Internet pour les machines privées | Via un proxy |

À la fin, accepte l'**aperçu** puis la **création**. Attends 2 à 5 minutes que felcloud affiche :

```
✓ Toutes les machines répondent en SSH.
```

Ton projet est rangé dans `~/felcloud-projets/<nom>/`.

## 4. Te connecter à tes machines

**Projet Terraform :**

```bash
cd ~/felcloud-projets/<nom>
terraform output ssh                # commande pour le bastion
terraform output ssh_via_rebond     # commandes pour les autres machines
```

**Projet Pulumi :**

```bash
cd ~/felcloud-projets/<nom>
set -x PULUMI_CONFIG_PASSPHRASE ""        # fish   (bash : export PULUMI_CONFIG_PASSPHRASE="")
pulumi stack output ssh --json
pulumi stack output ssh_via_rebond --json
```

Copie la commande affichée (sans les guillemets autour) et colle-la dans le terminal.

## 5. Tout supprimer quand tu as fini

```bash
felcloud destroy <nom>
```

Supprime tout sur FelCloud, puis le dossier du projet, puis sa clé SSH.

---

## Aide-mémoire

| Je veux... | Commande |
|---|---|
| créer un projet | `felcloud new` |
| voir mes projets | `felcloud projets` |
| vérifier que mes machines répondent | `felcloud test <nom>` |
| tout supprimer | `felcloud destroy <nom>` |
| tester mes identifiants | `felcloud check` |
| vérifier ma machine | `felcloud doctor` |
| tout faire par menus | `felcloud` |

## Problèmes fréquents

| Message | Solution |
|---|---|
| `felcloud: command not found` | Ajoute `~/.local/bin` au PATH (voir étape 1) |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | `ssh-keygen -R <IP>` puis reconnecte-toi (FelCloud réutilise les IP) |
| `Connection timed out` juste après la création | Attends 2 minutes : la machine démarre encore |
| `No configuration files` (Terraform) | Lance la commande **dans** le dossier du projet (`cd ~/felcloud-projets/<nom>`) |
| `passphrase must be set` (Pulumi) | Tape `set -x PULUMI_CONFIG_PASSPHRASE ""` dans ce terminal |
| `apt` échoue sur une machine sans IP publique | Recrée le projet avec le bastion et le proxy (étape 3) |

## À savoir

- **Ne crée pas tes projets dans `/tmp`** : il s'efface au redémarrage, et felcloud ne pourrait plus supprimer tes machines.
- **Supprime toujours avec `felcloud destroy`** : supprimer le dossier à la main laisse les machines tourner sur FelCloud.
- **Ne partage jamais** `~/.config/openstack/clouds.yaml` : il contient ton secret.

---

📖 Tout le détail (fichiers générés, sécurité, modification d'un projet, fonctionnement interne) : [docs/GUIDE.md](docs/GUIDE.md)
