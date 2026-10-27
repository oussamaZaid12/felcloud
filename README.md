# felcloud

**Crée tes machines virtuelles sur FelCloud en répondant à quelques questions.**

Tu choisis avec les flèches du clavier ce que tu veux (réseau, machines, IP publique, disques).
felcloud écrit le code **Terraform** ou **Pulumi** (Python, JavaScript ou Go) à ta place, crée tout sur FelCloud,
vérifie que les machines répondent, puis supprime tout proprement quand tu as fini.

---

## 1. Installer (une seule fois)

Fonctionne sous **Linux** (Ubuntu, Debian, Fedora, Arch...) et **macOS**. Copie cette ligne dans un terminal :

```bash
curl -fsSL https://raw.githubusercontent.com/oussamaZaid12/felcloud/main/install.sh | bash
```

Pas besoin de sudo ni de Python : si la machine n'a pas de Python récent, felcloud télécharge le sien.
À la fin, felcloud enchaîne directement sur la configuration (étape 2).
**Ouvre ensuite un nouveau terminal** pour que la commande `felcloud` soit reconnue.

## 2. Configurer (une seule fois)

Lance `felcloud setup` (déjà lancé automatiquement par l'installation). Il te demande deux choses.

### a. Tes identifiants : le fichier `clouds.yaml`

**Dans Skyline** : Menu → **User Center** → **Application Credentials** → crée un identifiant,
puis **télécharge le fichier `clouds.yaml`** (le secret n'est affiché qu'une seule fois).

Ce fichier doit être rangé exactement ici :

| Système | Emplacement |
|---|---|
| Linux | `/home/<ton-nom>/.config/openstack/clouds.yaml` |
| macOS | `/Users/<ton-nom>/.config/openstack/clouds.yaml` |

Le plus simple : dans `felcloud setup`, choisis **« J'ai téléchargé clouds.yaml depuis Skyline »**.
felcloud le trouve dans tes Téléchargements, le range à cet endroit, le protège (lisible par toi seul),
supprime la copie téléchargée et teste la connexion.
Réponds **Oui** à « Utiliser comme cloud par défaut ».

> Tu peux aussi choisir « Saisir mon ID et mon secret » et coller les deux valeurs affichées par Skyline.

### b. Le dossier de tes projets

felcloud te demande où ranger tes projets (par défaut `~/felcloud-projets`).
Choisis un dossier que tu gardes : **tous** tes projets y seront créés, chacun dans son sous-dossier.
Pour le changer plus tard : `felcloud setup` → « Changer le dossier de mes projets ».

### c. Vérifier

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

Ton projet est rangé dans `<dossier-des-projets>/<nom>/` : felcloud affiche la commande `cd` exacte.

## 4. Te connecter à tes machines

**Projet Terraform :**

```bash
cd <dossier-des-projets>/<nom>
terraform output ssh                # commande pour le bastion
terraform output ssh_via_rebond     # commandes pour les autres machines
```

**Projet Pulumi :**

```bash
cd <dossier-des-projets>/<nom>
export PULUMI_CONFIG_PASSPHRASE=""        # bash/zsh   (fish : set -x PULUMI_CONFIG_PASSPHRASE "")
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
| changer le dossier des projets | `felcloud setup` |
| désinstaller felcloud | `curl -fsSL https://raw.githubusercontent.com/oussamaZaid12/felcloud/main/install.sh \| bash -s -- --uninstall` |
| tout faire par menus | `felcloud` |

## Problèmes fréquents

| Message | Solution |
|---|---|
| `felcloud: command not found` | Ouvre un nouveau terminal (l'installation a ajouté `~/.local/bin` au PATH) |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | `ssh-keygen -R <IP>` puis reconnecte-toi (FelCloud réutilise les IP) |
| `Connection timed out` juste après la création | Attends 2 minutes : la machine démarre encore |
| `No configuration files` (Terraform) | Lance la commande **dans** le dossier du projet (`cd <dossier-des-projets>/<nom>`) |
| `passphrase must be set` (Pulumi) | Tape `export PULUMI_CONFIG_PASSPHRASE=""` dans ce terminal (fish : `set -x PULUMI_CONFIG_PASSPHRASE ""`) |
| `apt` échoue sur une machine sans IP publique | Recrée le projet avec le bastion et le proxy (étape 3) |

## À savoir

- **Ne crée pas tes projets dans `/tmp`** : il s'efface au redémarrage, et felcloud ne pourrait plus supprimer tes machines.
- **Supprime toujours avec `felcloud destroy`** : supprimer le dossier à la main laisse les machines tourner sur FelCloud.
- **Ne partage jamais** `~/.config/openstack/clouds.yaml` : il contient ton secret.

## Pour contribuer

```bash
git clone https://github.com/oussamaZaid12/felcloud.git
cd felcloud
./install.sh --dev      # le code du dépôt est utilisé directement
```

---

📖 Tout le détail (fichiers générés, sécurité, modification d'un projet, fonctionnement interne) : [docs/GUIDE.md](docs/GUIDE.md)
