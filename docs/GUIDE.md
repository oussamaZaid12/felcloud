# felcloud — guide complet

**Créer ton infrastructure OpenStack sur FelCloud, pas à pas, sans connaître Terraform ni Pulumi à l'avance.**

## En résumé

`felcloud` est un assistant dans le terminal, pensé pour les débutants. Tu choisis avec les flèches du clavier ce que tu veux (réseau, pare-feu, machines virtuelles, IP publique, disques), et felcloud :

1. **installe tes identifiants** FelCloud au bon endroit et vérifie qu'ils fonctionnent ;
2. **lit ton projet FelCloud en direct** (systèmes, tailles, réseaux, quotas) : tu ne peux choisir que ce qui existe vraiment ;
3. **écrit pour toi un projet Terraform ou Pulumi (Python)** complet, commenté et autonome, dans `~/felcloud-projets/<nom>/` ;
4. **crée l'infrastructure** après t'avoir montré un aperçu ;
5. **vérifie que chaque machine répond en SSH** et te donne les commandes de connexion ;
6. **supprime tout proprement** quand tu as fini.

Les particularités de FelCloud sont gérées automatiquement : accès Internet des machines privées par un bastion et son proxy, allocation fiable des IP publiques, IP réutilisées, rebond SSH vers les machines privées.

> **État actuel :** identifiants, génération et pilotage de projets **Terraform** et **Pulumi (Python)** terminés et testés sur FelCloud. Voir la [feuille de route](#feuille-de-route).

---

## Démarrage rapide

Suis ces étapes dans l'ordre. Les étapes 1 à 4 ne se font **qu'une seule fois**.

### Étape 1 — Vérifier ta machine

Il te faut **Linux**, **Python 3.10 ou plus** et **Git** :

```bash
python3 --version     # doit afficher 3.10 ou plus
git --version
```

S'il en manque un (Ubuntu/Debian) : `sudo apt install python3 python3-venv git`

### Étape 2 — Installer felcloud

```bash
git clone <URL-du-dépôt> FelcloudGuide
cd FelcloudGuide
./install.sh
```

Puis vérifie :

```bash
felcloud --version
```

Si le terminal répond `command not found`, ajoute `~/.local/bin` à ton PATH (le script t'a affiché la commande exacte), puis ouvre un nouveau terminal :

```bash
fish_add_path ~/.local/bin                                            # fish
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc   # bash
```

### Étape 3 — Créer tes identifiants dans Skyline

1. Connecte-toi à la console FelCloud (**Skyline**).
2. **Menu → User Center → Application Credentials**.
3. Crée un identifiant (donne-lui un nom, laisse le reste par défaut).
4. Copie l'**ID** et le **secret** affichés. ⚠️ Le secret n'est montré **qu'une seule fois**.

### Étape 4 — Donner tes identifiants à felcloud

```bash
felcloud setup
```

- Choisis **« Saisir mon ID et mon secret »**, colle les deux valeurs, et appuie sur Entrée pour les autres questions (les bonnes valeurs FelCloud sont proposées).
- Si ton fichier `~/.config/openstack/clouds.yaml` contient déjà tes identifiants, choisis plutôt **« Tester un cloud déjà configuré »**.

felcloud teste la connexion. Réponds **Oui** à « Utiliser comme cloud par défaut ».

Vérifie ensuite que tout est prêt :

```bash
felcloud doctor
```

Il te faut **au moins un** des deux outils. S'il en manque, installe celui que tu veux utiliser (sans sudo, somme de contrôle vérifiée) :

```bash
felcloud install terraform
felcloud install pulumi
```

### Étape 5 — Créer ton premier projet

```bash
felcloud new
```

Réponds aux questions (flèches pour choisir, **Espace** pour cocher, **Entrée** pour valider). En cas de doute, garde la réponse proposée : ce sont les choix recommandés. En particulier :

- **Outil** → Terraform (fichiers de configuration `.tf`) ou Pulumi (un programme Python) : les deux créent exactement la même infrastructure ;
- **Réseau** → « Créer un nouveau réseau » ;
- **Accès depuis Internet** → « Ajouter une VM bastion dédiée » ;
- **Internet pour les machines privées** → « Via un proxy ».

À la fin, accepte l'**aperçu** (rien n'est créé), puis la **création**. felcloud attend que les machines démarrent (2 à 5 minutes) et affiche :

```
✓ mon-projet-bastion : connexion SSH réussie
✓ mon-projet-vm : connexion SSH réussie
✓ Toutes les machines répondent en SSH.
```

### Étape 6 — Te connecter à tes machines

```bash
cd ~/felcloud-projets/mon-projet

# projet Terraform
terraform output ssh                # commande pour le bastion
terraform output ssh_via_rebond     # commandes pour les machines privées

# projet Pulumi
set -x PULUMI_CONFIG_PASSPHRASE ""  # fish ; en bash/zsh : export PULUMI_CONFIG_PASSPHRASE=""
pulumi stack output ssh --json
pulumi stack output ssh_via_rebond --json
```

Copie-colle la commande affichée (sans les guillemets qui l'entourent).

### Étape 7 — Tout supprimer quand tu as fini

```bash
felcloud destroy mon-projet
```

Les ressources sont supprimées du cloud, puis le dossier, puis la clé SSH.

### Aide-mémoire

| Je veux... | Commande |
|---|---|
| créer un projet | `felcloud new` |
| voir mes projets | `felcloud projets` |
| voir les IP et commandes SSH | `cd ~/felcloud-projets/<nom>` puis `terraform output` (ou `pulumi stack output`) |
| vérifier que tout répond | `felcloud test <nom>` |
| tout supprimer | `felcloud destroy <nom>` |
| tout faire par menus | `felcloud` |

Le reste de ce document détaille chaque étape et les cas particuliers.

---

## Sommaire

1. [Prérequis](#1-prérequis)
2. [Installation](#2-installation)
3. [Obtenir tes identifiants dans Skyline](#3-obtenir-tes-identifiants-dans-skyline)
4. [Installer tes identifiants](#4-installer-tes-identifiants)
5. [Vérifier que tout fonctionne](#5-vérifier-que-tout-fonctionne)
6. [Créer ton premier projet](#6-créer-ton-premier-projet)
7. [Comprendre le fichier clouds.yaml](#7-comprendre-le-fichier-cloudsyaml)
8. [Sécurité : les règles à respecter](#8-sécurité--les-règles-à-respecter)
9. [Toutes les commandes](#9-toutes-les-commandes)
10. [En cas de problème](#10-en-cas-de-problème)
11. [Désinstaller](#11-désinstaller)

---

## 1. Prérequis

| Élément | Comment vérifier | Si absent |
|---|---|---|
| Linux | — | felcloud ne fonctionne que sous Linux |
| Python 3.10 ou plus | `python3 --version` | `sudo apt install python3 python3-venv` (Ubuntu/Debian) |
| Git | `git --version` | `sudo apt install git` |
| Un compte FelCloud | accès à la console Skyline | demande-le à ton responsable ou à ton enseignant |

Pas besoin de droits administrateur (`sudo`) pour installer felcloud lui-même.

## 2. Installation

```bash
git clone <URL-du-dépôt> FelcloudGuide
cd FelcloudGuide
./install.sh
```

Le script :

1. vérifie que Python est assez récent,
2. crée un environnement isolé dans `~/.local/share/felcloud/` (rien n'est installé dans ton système),
3. installe les dépendances,
4. rend la commande `felcloud` disponible dans `~/.local/bin/`.

**Si le terminal répond `felcloud: command not found`**, c'est que `~/.local/bin` n'est pas dans ton `PATH`. Le script t'affiche la commande exacte à lancer selon ton shell :

```bash
# bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
# zsh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
# fish
fish_add_path ~/.local/bin
```

Vérifie ensuite :

```bash
felcloud --version
```

## 3. Obtenir tes identifiants dans Skyline

Pour qu'un programme puisse créer des ressources à ta place, il lui faut des identifiants. On n'utilise **pas** ton mot de passe : on crée une **application credential**, un couple *identifiant + secret* fait exprès pour les programmes.

1. Connecte-toi à la console FelCloud (**Skyline**).
2. Ouvre le menu, puis **User Center → Application Credentials**.
3. Crée un nouvel identifiant : donne-lui un nom parlant (par exemple `mon-pc-terraform`), laisse les autres options par défaut.
4. Skyline affiche un **ID** et un **secret**.

> ⚠️ **Le secret n'est affiché qu'une seule fois.** Copie-le immédiatement. Si tu le perds, il n'y a aucun moyen de le retrouver : il faudra créer une nouvelle application credential.

**Pourquoi pas ton mot de passe ?** Une application credential est limitée à un seul projet, peut être supprimée à tout moment sans changer ton mot de passe, et peut recevoir une date d'expiration. Si elle fuit, tu la supprimes dans Skyline et le problème est réglé.

## 4. Installer tes identifiants

Tous les outils OpenStack (felcloud, Terraform, Pulumi, la commande `openstack`) lisent le même fichier :

```
~/.config/openstack/clouds.yaml
```

Trois façons de le remplir, de la plus simple à la plus manuelle.

### Option A : laisser felcloud l'écrire (recommandé)

```bash
felcloud setup
```

Choisis **« Saisir mon ID et mon secret »**, puis colle les deux valeurs copiées depuis Skyline. Les autres questions ont déjà la bonne réponse proposée pour FelCloud : appuie simplement sur Entrée.

```
? Nom court pour ce cloud : felcloud
? Adresse d'authentification : https://identity.api.felcloud.io/v3/
? Région : North-Africa
? ID de l'application credential : 4b1e8f03...
? Secret (il ne s'affiche pas pendant la saisie) : ****************
✓ « felcloud » ajouté dans ~/.config/openstack/clouds.yaml (chmod 600)
✓ Connexion réussie à felcloud
```

felcloud crée le fichier s'il n'existe pas, **ajoute** ton cloud sans effacer les autres, garde une copie de sauvegarde de l'ancienne version, protège le fichier, puis teste la connexion.

### Option B : importer un fichier clouds.yaml

Si tu as déjà un fichier `clouds.yaml` (envoyé par un collègue, téléchargé, etc.) :

```bash
felcloud setup                                   # puis « Importer un fichier clouds.yaml »
felcloud setup --import ./clouds.yaml            # sans les menus
felcloud setup --import ./clouds.yaml --as projet-tp   # en le renommant
```

Si un cloud du même nom existe déjà, felcloud te demande quoi faire : garder les deux, renommer, remplacer ou ignorer.

### Option C : écrire le fichier toi-même

Crée ou complète `~/.config/openstack/clouds.yaml` :

```yaml
clouds:
  felcloud:
    auth:
      auth_url: https://identity.api.felcloud.io/v3/
      application_credential_id: "TON_ID"
      application_credential_secret: "TON_SECRET"
    region_name: North-Africa
    interface: public
    identity_api_version: 3
    auth_type: v3applicationcredential
```

Puis protège-le :

```bash
chmod 600 ~/.config/openstack/clouds.yaml
```

## 5. Vérifier que tout fonctionne

```bash
felcloud check felcloud
```

```
✓ Connexion réussie à felcloud
  Projet : 3f2a9c1e7b8d4e6f9a0b1c2d3e4f5a6b   Région : North-Africa
Utilisation du projet
┏━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓
┃ Ressource ┃ Utilisé ┃ Maximum ┃
┡━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩
│ Instances │       1 │      50 │
│ vCPU      │       1 │     128 │
│ RAM (Go)  │       1 │     256 │
└───────────┴─────────┴─────────┘
```

Puis vérifie que ta machine a tout ce qu'il faut :

```bash
felcloud doctor
```

Il contrôle Python, le client SSH, ton `clouds.yaml` et sa protection, ton cloud par défaut, et la présence de Terraform ou Pulumi. Pour chaque élément manquant, il affiche la commande qui l'installe. Terraform et Pulumi peuvent être installés directement :

```bash
felcloud install terraform
felcloud install pulumi
```

(téléchargement depuis le site officiel de HashiCorp, somme de contrôle vérifiée, installation dans `~/.local/bin`, sans `sudo`).

## 6. Créer ton premier projet

```bash
felcloud new
```

L'assistant te pose une série de questions. Pour chacune, une réponse raisonnable est déjà proposée : en cas de doute, appuie sur Entrée.

### Ce qu'il te demande

**1. Le projet.** Un nom court (par exemple `tp-reseau`) : il préfixe toutes les ressources créées, ce qui permet à plusieurs personnes de travailler sur le même projet FelCloud sans se gêner. Puis l'outil : **Terraform** (le projet est un ensemble de fichiers `.tf`) ou **Pulumi** (le projet est un programme : `__main__.py` en Python, `index.js` en JavaScript ou `main.go` en Go). Les deux créent exactement la même infrastructure ; avec Pulumi, l'état est rangé dans le dossier `.pulumi-state/` du projet, sans compte Pulumi.

**2. Ce que tu veux créer**, en cochant avec Espace :

| Brique | Ce que ça crée |
|---|---|
| Réseau complet | un réseau privé, sa plage d'adresses, et un routeur relié au réseau externe |
| Pare-feu | un security group : tu coches les ouvertures (SSH, HTTP, HTTPS, ping, trafic entre tes machines, ports libres) |
| Clé SSH | une clé dédiée au projet (recommandé), une de tes clés existantes, ou une clé déjà enregistrée sur le cloud |
| Machines virtuelles | le nombre, le système, la taille, les noms |
| Adresse IP publique | une **VM bastion dédiée** comme seule porte d'entrée (recommandé), ou une IP publique directement sur certaines de tes machines |
| Volumes | des disques supplémentaires, leur taille, leur type (NVMe rapide ou HDD économique), la machine à laquelle les attacher |

**3. Les détails de chaque brique.** Les listes de systèmes, de tailles, de réseaux et de types de disque sont **lues en direct sur FelCloud** : tu ne peux choisir que ce qui existe vraiment sur ton projet. L'assistant vérifie aussi tes quotas avant de générer.

**4. Un récapitulatif**, puis la génération.

```
Récapitulatif
┌──────────┬───────────────────────────────────────────────────────────────────┐
│ Projet   │ tp-reseau  (Terraform, cloud felcloud)                            │
│ Réseau   │ nouveau, 10.0.10.0/24, sortie via INTERNET                        │
│ Pare-feu │ SSH (port 22), HTTP (port 80), Ping (ICMP), Trafic libre...       │
│ Clé SSH  │ nouvelle : ~/.ssh/tp-reseau-key                                   │
│ Machine  │ tp-reseau-vm-1 · G0.basic.1c2g · Ubuntu 24.04 + IP publique + ... │
│ Machine  │ tp-reseau-vm-2 · G0.basic.1c2g · Ubuntu 24.04 (Internet via proxy)│
└──────────┴───────────────────────────────────────────────────────────────────┘
```

### L'accès à Internet sur FelCloud

**Sur FelCloud, seule une machine qui a une IP publique accède à Internet.** Une machine sans IP publique ne peut donc ni faire `apt install`, ni `pip install`, ni `git clone`.

D'où le choix recommandé de l'assistant : **une VM bastion dédiée**. C'est une petite machine (la plus petite taille disponible) qui reçoit la seule IP publique du projet. Elle sert à deux choses :

- **porte d'entrée SSH** : tu te connectes au bastion, puis de là à tes machines (`terraform output ssh_via_rebond` donne les commandes toutes prêtes) ;
- **proxy Internet** : un proxy Squid y est installé automatiquement, et tes machines sont configurées pour passer par lui. `apt`, `pip` ou `git` fonctionnent comme si elles avaient Internet.

Tes machines de travail restent privées : seul le bastion est exposé sur Internet. Tu peux quand même donner une IP publique à certaines machines (par exemple un serveur web), ou te passer de bastion et mettre l'IP publique directement sur tes machines.

### Où sont rangés tes projets

Chaque projet est créé dans **`~/felcloud-projets/<nom>/`**, un dossier permanent. Ne crée pas de projet dans `/tmp` : ce dossier est effacé au redémarrage, et avec lui le fichier `terraform.tfstate`, sans lequel Terraform ne sait plus quoi supprimer sur le cloud. felcloud t'avertit si tu essaies.

| Quoi | Où |
|---|---|
| Tes projets | `~/felcloud-projets/<nom>/` |
| Clé SSH d'un projet | `~/.ssh/<nom>-key` (privée) et `~/.ssh/<nom>-key.pub` (publique) |
| Tes identifiants | `~/.config/openstack/clouds.yaml` |
| Préférences de felcloud | `~/.config/felcloud/config.yaml` |
| Les ressources créées | sur FelCloud : Skyline, ou `openstack --os-cloud <cloud> server list` |

### Ce qui est généré

Un projet Terraform **complet, commenté et autonome** :

```
~/felcloud-projets/tp-reseau/
├── README.md             explique CE projet : ressources, commandes, connexion SSH
├── provider.tf           connexion au cloud (aucun secret dedans)
├── network.tf            réseau, sous-réseau, routeur
├── security.tf           pare-feu
├── keypair.tf            ta clé SSH publique
├── instances.tf          les machines — leur liste est en haut du fichier
├── volumes.tf            les volumes
├── outputs.tf            les adresses et commandes SSH affichées à la fin
├── cloud-init-*.yaml     scripts de premier démarrage (proxy, nginx)
├── felcloud.yaml         tes réponses, pour regénérer le projet
└── terraform.tfstate     créé par Terraform : l'inventaire de ce qui existe. Ne jamais le supprimer
```

### Le cycle de vie d'un projet

**Créer**

```bash
felcloud new
```

À la fin, felcloud propose un **aperçu** (rien n'est créé), puis la **création**. Il applique alors exactement le plan affiché, puis **vérifie automatiquement que chaque machine répond en SSH**. Ça prend 2 à 5 minutes, le temps qu'elles démarrent :

```
── Vérification de la connexion SSH ──
✓ tp-reseau-bastion : connexion SSH réussie
✓ tp-reseau-vm : connexion SSH réussie
✓ Toutes les machines répondent en SSH.
```

Si une machine ne répond pas, felcloud explique pourquoi : pare-feu, réseau ou routeur en panne, mauvaise clé.

**Voir**

```bash
felcloud projets                  # tous tes projets, déployés ou non
cd ~/felcloud-projets/tp-reseau
terraform output                  # adresses IP et commandes SSH
terraform output ssh              # se connecter aux machines publiques
terraform output ssh_via_rebond   # se connecter aux machines privées (via le bastion)
felcloud test tp-reseau           # revérifier que tout répond
```

**Modifier** : toujours **depuis le dossier du projet** (sinon Terraform répond `No configuration files`) :

```bash
cd ~/felcloud-projets/tp-reseau
nano instances.tf                 # par ex. ajoute une machine dans la liste du haut
terraform plan                    # lis la ligne « Plan: » : un « to destroy » inattendu = machine recréée
terraform apply
```

**Supprimer**

```bash
felcloud destroy tp-reseau
```

Dans l'ordre et sans rien oublier : suppression de tout sur le cloud (avec une nouvelle tentative automatique en cas de coupure passagère de l'API), puis du dossier, puis de la clé SSH. Chaque étape est confirmée.

**Regénérer** un projet à partir de ses réponses, sans repasser par les questions :

```bash
felcloud new --answers ~/felcloud-projets/tp-reseau/felcloud.yaml --output ~/felcloud-projets/tp-reseau-2
```

Le `README.md` de chaque projet détaille tout le reste : connexion aux machines privées, volumes, modification.

### Réseau neuf ou réseau existant ?

Choisis **« Créer un nouveau réseau »** (recommandé). Avec un réseau existant, tes machines dépendent d'un routeur que le projet ne gère pas. S'il est en panne côté FelCloud, elles sont injoignables, même avec une IP publique. felcloud indique de quel routeur dépend chaque réseau, refuse ceux qui n'en ont pas quand une IP publique est demandée, et la vérification SSH après création détecte la panne.

## 7. Comprendre le fichier clouds.yaml

```yaml
clouds:                       # la liste de tous tes clouds
  felcloud:                   # le NOM que tu choisis ; c'est lui qu'on donne aux outils
    auth:
      auth_url: https://identity.api.felcloud.io/v3/   # le service d'authentification (Keystone)
      application_credential_id: "..."                 # l'identifiant, non secret
      application_credential_secret: "..."             # le secret : à protéger
    region_name: North-Africa                          # la région FelCloud
    interface: public                                  # passer par les adresses publiques
    identity_api_version: 3                            # version de l'API d'identité
    auth_type: v3applicationcredential                 # on s'authentifie par application credential
```

Tu peux y ranger **plusieurs clouds** (un par projet, par exemple), chacun sous un nom différent. Les outils choisissent celui qu'on leur désigne :

| Outil | Comment lui donner le nom |
|---|---|
| felcloud | `felcloud check felcloud`, ou cloud par défaut choisi dans `felcloud setup` |
| commande openstack | `openstack --os-cloud felcloud server list` |
| Terraform | `provider "openstack" { cloud = "felcloud" }` |
| Pulumi | `openstack.Provider("p", cloud="felcloud")` |
| n'importe lequel | `export OS_CLOUD=felcloud` |

**Ce qui se passe à la connexion :** l'outil lit ton entrée, envoie l'ID et le secret au service d'authentification, et reçoit en échange un **jeton temporaire** (valable quelques heures). Toutes les opérations suivantes utilisent ce jeton. Le secret ne circule donc qu'une fois par session.

## 8. Sécurité : les règles à respecter

1. **Ne jamais versionner `clouds.yaml`** dans Git, ni le copier dans un projet. Il reste dans `~/.config/openstack/`. Le `.gitignore` de ce dépôt l'exclut par précaution.
2. **Le fichier doit être lisible par toi seul** (`chmod 600`). felcloud le fait automatiquement et `felcloud doctor` te prévient sinon.
3. **Ne jamais coller ton secret** dans un message, un ticket ou une capture d'écran.
4. **Après un import, supprime le fichier source** (dans tes téléchargements par exemple) : il contient ton secret en clair.
5. **En cas de doute, révoque** : supprime l'application credential dans Skyline et crée-en une nouvelle. C'est sans conséquence sur ton compte.

## 9. Toutes les commandes

| Commande | Rôle |
|---|---|
| `felcloud` | menu principal (tout est accessible par les flèches) |
| `felcloud setup` | installer, importer ou tester des identifiants |
| `felcloud setup --import FICHIER [--as NOM]` | importer un clouds.yaml sans les menus |
| `felcloud check [NOM]` | tester la connexion à un cloud |
| `felcloud clouds` | lister les clouds configurés (sans afficher les secrets) |
| `felcloud doctor` | vérifier que la machine est prête |
| `felcloud install terraform` | installer Terraform sans sudo |
| `felcloud install pulumi` | installer Pulumi sans sudo |
| `felcloud install node` | installer Node.js (Pulumi en JavaScript) |
| `felcloud install go` | installer Go (Pulumi en Go) |
| `felcloud new` | créer un nouveau projet avec l'assistant (dans `~/felcloud-projets/`) |
| `felcloud new --answers FICHIER [--output DOSSIER]` | regénérer un projet à partir de ses réponses |
| `felcloud projets` | lister tes projets et leur état |
| `felcloud test [PROJET]` | vérifier que les machines d'un projet répondent en SSH |
| `felcloud destroy [PROJET]` | supprimer un projet : cloud, dossier, clé |
| `felcloud --help` | aide |

Dans les menus : **flèches** pour se déplacer, **Entrée** pour valider, **Espace** pour cocher, **Ctrl+C** pour quitter à tout moment.

## 10. En cas de problème

| Message affiché | Cause | Solution |
|---|---|---|
| *Cette application credential n'existe plus* | Supprimée ou expirée dans Skyline | En créer une nouvelle, puis `felcloud setup` |
| *Identifiants refusés : le secret est incorrect* | Faute de copie du secret | Recopier le secret ; s'il est perdu, créer une nouvelle application credential |
| *Impossible de joindre l'adresse d'authentification* | Pas d'Internet, VPN requis, ou `auth_url` erronée | Vérifier la connexion ; comparer `auth_url` avec la section 7 |
| *Erreur de certificat HTTPS* | Certificat d'entreprise non reconnu | Ajouter `cacert: /chemin/vers/le.crt` dans l'entrée du cloud |
| *Ce nom de cloud n'existe pas* | Faute de frappe dans le nom | `felcloud clouds` pour voir les noms exacts |
| *Le fichier ne contient pas de section « clouds: »* | Mauvais fichier sélectionné | Vérifier qu'il commence bien par `clouds:` |
| `felcloud: command not found` | `~/.local/bin` absent du PATH | Voir la section 2 |
| Terraform : *No configuration files* | Commande lancée hors du dossier du projet | `cd` dans le dossier du projet, puis relancer |
| Terraform : *OpenStack connection error* ou *EOF* | Coupure passagère de l'API | Relancer la même commande : Terraform reprend où il s'était arrêté |
| Terraform : *no file exists at ~/.ssh/...pub* | La clé SSH du projet a été supprimée | Ne la supprime qu'après `terraform destroy` ; pour détruire quand même, recrée une clé au même chemin (`ssh-keygen -f ~/.ssh/<projet>-key`) |
| SSH : *Permission denied (publickey)* | Mauvaise clé, ou mauvais utilisateur pour l'image | Utiliser la commande de `terraform output ssh` telle quelle |
| `felcloud test` : *aucune réponse sur le port 22* | Pare-feu sans SSH, ou routeur en panne côté FelCloud | Vérifier la règle SSH ; sur un réseau existant, regénérer avec un réseau neuf ; sinon contacter le support avec l'IP |
| SSH : *Connection timed out* juste après `terraform apply` | La machine n'a pas fini de démarrer | Attendre 1 à 2 minutes |
| SSH : *REMOTE HOST IDENTIFICATION HAS CHANGED* | La machine a été recréée avec la même IP | `ssh-keygen -R <IP>` puis reconnecter |
| `apt` ou `pip` échoue sur une machine sans IP publique | Sur FelCloud, pas d'Internet sans IP publique | Regénérer avec le proxy (section 6), ou lui donner une IP publique |
| *Quota insuffisant* | Le projet n'a plus assez de machines, CPU, RAM ou IP | Détruire d'anciens projets ou demander une hausse de quota |

Pour aller plus loin dans le diagnostic, la commande officielle donne le message brut :

```bash
openstack --os-cloud felcloud token issue
```

## 11. Désinstaller

```bash
./install.sh --uninstall
```

Tes identifiants (`~/.config/openstack/clouds.yaml`), tes préférences (`~/.config/felcloud/`) et tes projets ne sont pas supprimés.

---

## Feuille de route

| Étape | Contenu | État |
|---|---|---|
| 1 | Installation, gestion et vérification des identifiants | ✅ terminé |
| 2 | `felcloud new` : générer un projet **Terraform** (réseau, security group, clé SSH, instances, volume, IP flottante, proxy Internet), avec les flavors et images lus en direct sur le cloud | ✅ terminé |
| 3 | Pilotage des projets : aperçu et création intégrés, vérification SSH automatique, `felcloud projets`, `felcloud test`, `felcloud destroy`, bastion dédié | ✅ terminé |
| 4 | Même chose en **Pulumi** : Python, JavaScript et Go ; mêmes questions, même infrastructure, état local au projet | ✅ terminé |
| 5 | Tests automatiques de toutes les combinaisons, exemples prêts à lire | à venir |

## Pour les contributeurs

```bash
./install.sh --dev        # le code du dépôt est utilisé en direct, sans réinstaller
```

```
FelcloudGuide/
├── install.sh              installation / désinstallation
├── pyproject.toml          dépendances Python
└── felcloud/
    ├── cli.py              commandes et menu principal
    ├── setup_cmd.py        felcloud setup / check / clouds
    ├── credentials.py      lecture, import, sauvegarde et protection de clouds.yaml
    ├── cloud.py            connexion OpenStack, lecture des ressources, messages d'erreur
    ├── wizard.py           les questions de `felcloud new` (communes à tous les outils)
    ├── generator.py        réponses + templates → projet
    ├── runner.py           lancement de terraform init / plan
    ├── doctor.py           vérification de la machine
    ├── installer.py        installation de Terraform
    ├── config.py           préférences (~/.config/felcloud/config.yaml)
    ├── ui.py               menus et affichage
    └── templates/
        ├── common/         README du projet, .gitignore, scripts cloud-init
        ├── terraform/      un template par brique (network, security, instances...)
        ├── pulumi-python/      Pulumi.yaml, requirements.txt, __main__.py
        ├── pulumi-javascript/  Pulumi.yaml, package.json, index.js
        └── pulumi-go/          Pulumi.yaml, go.mod, main.go
```

Les questions ne sont écrites qu'une fois (`wizard.py`) et produisent un dictionnaire de réponses indépendant de l'outil, enregistré dans `felcloud.yaml`. Chaque outil n'a besoin que de ses templates : ajouter un langage Pulumi (TypeScript, C#...), c'est ajouter `templates/pulumi-<langage>/`.

Pour tester sans toucher à ton vrai `clouds.yaml`, pointe vers un autre fichier avec la variable standard d'OpenStack :

```bash
OS_CLIENT_CONFIG_FILE=/tmp/essai/clouds.yaml felcloud setup
```
