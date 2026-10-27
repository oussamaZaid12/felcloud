"""`felcloud new` : les questions posées à l'utilisateur.

Les réponses forment un dictionnaire indépendant de l'outil (Terraform ou Pulumi).
Il est enregistré dans `felcloud.yaml` du projet généré, puis transformé en code
par les templates de l'outil choisi.
"""

import ipaddress
import re
import subprocess
from pathlib import Path

from rich.table import Table

from felcloud import cloud, config, credentials, ui

TOOLS = {
    "terraform": "Terraform",
    "pulumi-python": "Pulumi (Python)",
    "pulumi-javascript": "Pulumi (JavaScript)",
    "pulumi-go": "Pulumi (Go)",
}

# Programmes nécessaires pour chaque outil : (commande, nom affiché, commande d'installation).
REQUIREMENTS = {
    "terraform": [("terraform", "Terraform", "felcloud install terraform")],
    "pulumi-python": [("pulumi", "Pulumi", "felcloud install pulumi")],
    "pulumi-javascript": [("pulumi", "Pulumi", "felcloud install pulumi"),
                          ("node", "Node.js", "felcloud install node"),
                          ("npm", "npm", "felcloud install node")],
    "pulumi-go": [("pulumi", "Pulumi", "felcloud install pulumi"), ("go", "Go", "felcloud install go")],
}


def missing_requirements(tool):
    from felcloud import doctor

    return [(label, how) for cmd, label, how in REQUIREMENTS[tool] if not doctor.find_tool(cmd)]

BRICKS = [
    ("network", "Réseau complet", "réseau privé + sous-réseau + routeur relié à Internet", True),
    ("security_group", "Pare-feu (security group)", "ports ouverts : SSH, HTTP...", True),
    ("keypair", "Clé SSH", "pour te connecter aux machines sans mot de passe", True),
    ("instances", "Machines virtuelles", "image, taille, nombre", True),
    ("floating_ip", "Adresse IP publique", "rendre une ou plusieurs machines joignables depuis Internet", True),
    ("volumes", "Volumes de stockage", "disques supplémentaires attachés aux machines", False),
]

SG_RULES = [
    ("ssh", "SSH (port 22) — se connecter aux machines", True),
    ("http", "HTTP (port 80) — site web", False),
    ("https", "HTTPS (port 443) — site web sécurisé", False),
    ("icmp", "Ping (ICMP) — tester la connectivité", True),
    ("internal", "Trafic libre entre les machines du projet", True),
]

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")


def _valid_project(value):
    if not NAME_RE.match(value):
        return "3 à 32 caractères : minuscules, chiffres et tirets, en commençant par une lettre."
    if (config.PROJECTS_DIR / value).exists():
        return f"Le projet {config.PROJECTS_DIR / value} existe déjà : choisis un autre nom."
    return True


def _valid_cidr(value):
    try:
        net = ipaddress.ip_network(value.strip(), strict=True)
    except ValueError:
        return "Format attendu : 10.0.5.0/24"
    if net.version != 4 or not net.is_private:
        return "Utilise une plage privée IPv4 (10.x.x.x, 172.16-31.x.x ou 192.168.x.x)."
    if net.prefixlen > 28:
        return "Plage trop petite : /28 au minimum (par exemple /24)."
    return True


def _valid_ports(value):
    if not value.strip():
        return True
    for part in value.replace(" ", "").split(","):
        if not part.isdigit() or not 1 <= int(part) <= 65535:
            return f"« {part} » n'est pas un port valide (1 à 65535). Exemple : 8080,3000"
    return True


def _valid_int(low, high):
    def check(value):
        if not value.strip().isdigit() or not low <= int(value) <= high:
            return f"Entre un nombre entre {low} et {high}."
        return True
    return check


def _remaining(limits, key):
    used, maximum = limits.get(key, (0, -1))
    return None if maximum in (-1, None) else maximum - used


def ask_project():
    ui.section("Projet")
    name = ui.text("Nom du projet (il préfixera toutes les ressources) :", default="mon-projet",
                   validate=_valid_project)
    choices = []
    for key, label in TOOLS.items():
        missing = missing_requirements(key)
        if missing:
            label += f"   (à installer : {', '.join(sorted({m for m, _ in missing}))})"
        choices.append(ui.Choice(label, value=key))
    tool = ui.select("Avec quel outil ? (tous créent exactement la même infrastructure)", choices)
    missing = missing_requirements(tool)
    if missing:
        ui.warn(f"{TOOLS[tool]} a besoin de : {', '.join(sorted({m for m, _ in missing}))}. "
                "Le projet sera généré, mais il faudra l'installer avant de le lancer :")
        for how in sorted({h for _, h in missing}):
            ui.hint(how)
    return name, tool


def ask_cloud():
    clouds = list(credentials.installed_clouds())
    if not clouds:
        raise ui.Abort("Aucun cloud configuré : lance d'abord « felcloud setup ».")
    default = config.default_cloud()
    if len(clouds) == 1:
        return clouds[0]
    return ui.select("Sur quel cloud ?", clouds, default=default if default in clouds else None)


def ask_bricks():
    choices = [ui.Choice(f"{label}  — {desc}", value=key, checked=checked)
               for key, label, desc, checked in BRICKS]
    return ui.checkbox("Que veux-tu créer ?", choices,
                       validate=lambda picked: True if picked else "Coche au moins un élément.")


def ask_network(project, found, needs_internet):
    ui.section("Réseau")
    net = {}
    if found.project_networks:
        mode = ui.select("Réseau des machines :", [
            ui.Choice("Créer un nouveau réseau dédié à ce projet (recommandé)", value="create"),
            ui.Choice("Utiliser un réseau existant du projet", value="existing"),
        ])
    else:
        mode = "create"

    if mode == "existing":
        choices = []
        for n in found.project_networks:
            via = f"routeur {n['router']}" if n.get("router") else "aucun routeur vers l'extérieur"
            unusable = needs_internet and not n.get("router")
            choices.append(ui.Choice(f"{n['name']}  {', '.join(n['cidrs'])}  ({via})", value=n,
                                     disabled="pas d'IP publique possible" if unusable else None))
        if all(c.disabled for c in choices):
            ui.warn("Aucun réseau existant n'est relié à un routeur vers l'extérieur : "
                    "un nouveau réseau va être créé.")
            mode = "create"
        else:
            chosen = ui.select("Lequel ?", choices)
            net = {"mode": "existing", "name": chosen["name"], "id": chosen["id"]}
            ui.warn(f"Tes machines dépendront du routeur « {chosen.get('router') or 'aucun'} », qui n'est pas "
                    "géré par ce projet. S'il est en panne, elles seront injoignables : felcloud le "
                    "vérifiera après la création.")
            if not ui.confirm("Continuer avec ce réseau existant ?", default=True):
                mode = "create"

    if mode == "create":
        used = {c for n in found.project_networks for c in n["cidrs"]}
        default_cidr = next(f"10.0.{i}.0/24" for i in range(10, 250) if f"10.0.{i}.0/24" not in used)
        cidr = ui.text("Plage d'adresses privées :", default=default_cidr, validate=_valid_cidr)
        net = {"mode": "create", "cidr": cidr.strip(), "dns": ["1.1.1.1", "8.8.8.8"]}
        ui.hint("DNS 1.1.1.1 et 8.8.8.8 configurés : les machines pourront résoudre les noms (apt, pip...).")

    if mode == "create" or needs_internet:
        net["external_network"] = ask_external_network(found)
    return net


def ask_external_network(found):
    if not found.external_networks:
        raise ui.Abort("Aucun réseau externe n'est visible sur ce projet : impossible d'accéder à Internet.")
    if len(found.external_networks) == 1:
        return found.external_networks[0]["name"]
    choices = []
    for n in found.external_networks:
        recommended = n is found.external_networks[0]
        label = n["name"] + ("   ← accès Internet (recommandé)" if recommended else "   (usage interne)")
        choices.append(ui.Choice(label, value=n["name"]))
    return ui.select("Réseau externe (passerelle vers Internet, source des IP publiques) :", choices)


def ask_security_group():
    ui.section("Pare-feu")
    ui.hint("Par défaut, tout le trafic entrant est bloqué. Coche ce que tu veux autoriser.")
    rules = ui.checkbox("Autoriser :", [ui.Choice(label, value=key, checked=checked)
                                         for key, label, checked in SG_RULES])
    sg = {"rules": rules, "ssh_cidr": "0.0.0.0/0", "custom_tcp_ports": []}
    if "ssh" in rules:
        sg["ssh_cidr"] = ui.text("SSH autorisé depuis (0.0.0.0/0 = partout) :", default="0.0.0.0/0",
                                 validate=_valid_source).strip()
    ports = ui.text("Autres ports TCP à ouvrir (ex. 8080,3000 — vide pour aucun) :", validate=_valid_ports)
    sg["custom_tcp_ports"] = [int(p) for p in ports.replace(" ", "").split(",") if p]
    return sg


def _valid_source(value):
    try:
        ipaddress.ip_network(value.strip(), strict=False)
        return True
    except ValueError:
        return "Format attendu : 0.0.0.0/0 ou une adresse précise comme 197.5.10.20/32"


def _public_keys():
    """Clés publiques locales dont la clé privée correspondante existe et correspond vraiment."""
    valid = []
    for pub in sorted((Path.home() / ".ssh").glob("*.pub")):
        private = pub.with_suffix("")
        if not private.exists():
            continue
        try:
            derived = subprocess.run(["ssh-keygen", "-y", "-f", str(private)], capture_output=True,
                                     text=True, timeout=5, stdin=subprocess.DEVNULL).stdout.split()[:2]
        except (OSError, subprocess.TimeoutExpired):
            continue
        if derived and derived == pub.read_text().split()[:2]:
            valid.append(pub)
    return valid


def ask_keypair(project, found):
    ui.section("Clé SSH")
    key_name = f"{project}-key"
    key_path = Path.home() / ".ssh" / key_name
    local = _public_keys()
    choices = [ui.Choice(f"Créer une nouvelle clé dédiée ({key_path}) — recommandé", value="generate")]
    if local:
        choices.append(ui.Choice("Utiliser une de mes clés existantes", value="file"))
    if found.keypairs:
        choices.append(ui.Choice("Utiliser une clé déjà enregistrée sur le cloud", value="existing"))
    mode = ui.select("Quelle clé utiliser ?", choices)

    if mode == "existing":
        name = ui.select("Laquelle ?", found.keypairs)
        ui.hint("Il te faudra la clé privée correspondante sur ta machine pour te connecter.")
        return {"mode": "existing", "name": name, "private_key_path": ""}

    if key_name in found.keypairs:
        key_name = f"{key_name}-2"
    if mode == "file":
        pub = ui.select("Laquelle ? (seules les clés dont la partie privée est présente sont proposées)",
                        [ui.Choice(str(p), value=p) for p in local])
        return {"mode": "file", "name": key_name, "public_key_path": _tilde(pub),
                "private_key_path": _tilde(pub.with_suffix(""))}

    if key_path.exists() or key_path.with_suffix(".pub").exists():
        ui.info(f"{key_path} existe déjà : elle sera réutilisée.")
    return {"mode": "generate", "name": key_name, "public_key_path": _tilde(key_path) + ".pub",
            "private_key_path": _tilde(key_path)}


def _tilde(path):
    path = Path(path)
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def ask_instances(project, found, want_floating_ip):
    ui.section("Machines virtuelles")
    count = int(ui.text("Combien de machines ?", default="1", validate=_valid_int(1, 20)))
    image = ui.select("Système (image) :", found.images)
    flavor = ui.select("Taille (flavor) :", [ui.Choice(f.label, value=f.name) for f in found.flavors])

    names = []
    if count == 1:
        names = [ui.text("Nom de la machine :", default=f"{project}-vm", validate=_valid_vm_name).strip()]
    else:
        base = ui.text("Préfixe des noms (les machines seront numérotées) :", default=f"{project}-vm",
                       validate=_valid_vm_name).strip()
        names = [f"{base}-{i}" for i in range(1, count + 1)]

    public, bastion = set(), None
    if want_floating_ip:
        public, bastion = _ask_public_access(project, names, image, found)

    apt = cloud.is_apt_based(image)
    proxy = _ask_internet_access(names, public, apt, bastion)
    online = public | ({n for n in names if n not in public} if proxy else set())

    nginx = False
    if apt and online:
        nginx = ui.confirm("Installer automatiquement un serveur web (nginx) au démarrage ?", default=False)
        if nginx and len(online) < len(names):
            ui.warn("nginx ne sera installé que sur les machines qui ont accès à Internet.")

    user = cloud.ssh_user_for(image)
    vms = [{"name": n, "image": image, "flavor": flavor, "floating_ip": n in public,
            "nginx": nginx and n in online, "ssh_user": user, "role": ""} for n in names]
    if bastion:
        vms.insert(0, bastion)
    return vms, proxy


def _ask_public_access(project, names, image, found):
    """Choisit comment l'infrastructure est joignable depuis Internet.

    Retourne (machines de l'utilisateur ayant une IP publique, VM bastion dédiée ou None).
    """
    bastion_name = f"{project}-bastion"
    mode = ui.select("Comment accéder à tes machines depuis Internet ?", [
        ui.Choice(f"Ajouter une VM bastion dédiée ({bastion_name}) : seule porte d'entrée, "
                  "tes machines restent privées (recommandé)", value="bastion",
                  disabled=None if bastion_name not in names else "nom déjà utilisé"),
        ui.Choice("Donner une IP publique directement à certaines de mes machines", value="direct"),
    ])

    if mode == "direct":
        if len(names) == 1:
            return {names[0]}, None
        picked = ui.checkbox("Quelles machines reçoivent une IP publique ?",
                             [ui.Choice(n, value=n, checked=(i == 0)) for i, n in enumerate(names)],
                             validate=lambda p: True if p else "Coche au moins une machine.")
        return set(picked), None

    # Le bastion n'a besoin que de peu de ressources : la plus petite taille suffit.
    # Il doit tourner sous Ubuntu/Debian pour pouvoir héberger le proxy.
    flavor = min(found.flavors, key=lambda f: (f.vcpus, f.ram_mb, f.disk_gb))
    bastion_image = image if cloud.is_apt_based(image) else \
        next((i for i in found.images if cloud.is_apt_based(i)), image)
    ui.info(f"Bastion : {bastion_name} · {flavor.name} · {bastion_image}")
    bastion = {"name": bastion_name, "image": bastion_image, "flavor": flavor.name, "floating_ip": True,
               "nginx": False, "ssh_user": cloud.ssh_user_for(bastion_image), "role": "bastion"}

    picked = ui.checkbox("Certaines de tes machines ont-elles AUSSI besoin d'une IP publique "
                         "(ex. serveur web) ? Rien à cocher sinon.",
                         [ui.Choice(n, value=n) for n in names])
    return set(picked), bastion


def _ask_internet_access(names, public, apt, bastion=None):
    """Sur FelCloud, seules les machines avec une IP publique accèdent à Internet.

    Pour les autres, on propose un proxy installé sur le bastion (dédié, ou une des
    machines publiques). Retourne {"bastion": nom} ou None.
    """
    private = [n for n in names if n not in public]
    if not private:
        return None
    ui.info("Sur FelCloud, seule une machine avec une IP publique accède à Internet.")
    if not public and not bastion:
        ui.warn("Aucune machine n'a d'IP publique : aucune ne pourra installer de paquets (apt, pip...).")
        return None
    if not apt:
        ui.warn("Le proxy automatique n'est proposé que pour Ubuntu et Debian : "
                "les machines sans IP publique n'auront pas Internet.")
        return None
    proxy_host = bastion["name"] if bastion else sorted(public, key=names.index)[0]
    choice = ui.select("Accès à Internet pour les machines sans IP publique (installer des paquets) ?", [
        ui.Choice(f"Via un proxy installé sur {proxy_host} (recommandé)", value="proxy"),
        ui.Choice("Pas d'accès à Internet", value="none"),
    ])
    if choice == "none":
        return None
    if not bastion and len(public) > 1:
        proxy_host = ui.select("Quelle machine sert de proxy ?", sorted(public, key=names.index))
    return {"bastion": proxy_host}


def _valid_vm_name(value):
    return True if NAME_RE.match(value.strip()) else \
        "3 à 32 caractères : minuscules, chiffres et tirets, en commençant par une lettre."


def ask_volumes(project, found, instances):
    ui.section("Volumes")
    count = int(ui.text("Combien de volumes ?", default="1", validate=_valid_int(1, 10)))
    size = int(ui.text("Taille de chaque volume (Go) :", default="10", validate=_valid_int(1, 2000)))
    vtype = ""
    if found.volume_types:
        vtype = ui.select("Type de stockage :", [
            ui.Choice(f"{t}" + ("   ← rapide (SSD)" if t.lower() == "nvme" else
                                "   ← économique, plus lent" if t.lower() == "hdd" else ""), value=t)
            for t in found.volume_types])
    volumes = []
    for i in range(1, count + 1):
        name = f"{project}-data-{i}" if count > 1 else f"{project}-data"
        attach = None
        if instances:
            options = [ui.Choice(vm["name"], value=vm["name"]) for vm in instances]
            options.append(ui.Choice("Ne pas l'attacher pour l'instant", value=None))
            default_vm = instances[(i - 1) % len(instances)]["name"]
            attach = ui.select(f"Attacher « {name} » à :", options, default=default_vm)
        volumes.append({"name": name, "size": size, "type": vtype, "attach_to": attach})
    return volumes


def check_quotas(answers, found):
    """Avertit si le projet n'a pas assez de quota. Retourne False en cas de dépassement certain."""
    flavors = {f.name: f for f in found.flavors}
    vms = answers.get("instances") or []
    needs = {
        "instances": len(vms),
        "cores": sum(flavors[v["flavor"]].vcpus for v in vms),
        "ram_mb": sum(flavors[v["flavor"]].ram_mb for v in vms),
        "floating_ips": sum(v["floating_ip"] for v in vms),
        "volumes": len(answers.get("volumes") or []),
        "volume_gb": sum(v["size"] for v in answers.get("volumes") or []),
    }
    labels = {"instances": "machines", "cores": "vCPU", "ram_mb": "Mo de RAM",
              "floating_ips": "IP publiques", "volumes": "volumes", "volume_gb": "Go de volumes"}
    ok = True
    for key, need in needs.items():
        left = _remaining(found.limits, key)
        if need and left is not None and need > left:
            ui.err(f"Quota insuffisant : {need} {labels[key]} demandés, {left} disponibles sur le projet.")
            ok = False
    return ok


def summary(answers):
    table = Table(title="Récapitulatif", title_justify="left", show_header=False)
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Projet", f"{answers['project']}  ({TOOLS[answers['tool']]}, cloud {answers['cloud']})")
    net = answers.get("network")
    if net:
        table.add_row("Réseau", f"nouveau, {net['cidr']}, sortie via {net['external_network']}"
                      if net["mode"] == "create" else f"existant : {net['name']}")
    sg = answers.get("security_group")
    if sg:
        rules = [label.split(" —")[0] for key, label, _ in SG_RULES if key in sg["rules"]]
        rules += [f"TCP {p}" for p in sg["custom_tcp_ports"]]
        table.add_row("Pare-feu", ", ".join(rules) or "aucune ouverture")
    kp = answers.get("keypair")
    if kp:
        table.add_row("Clé SSH", {"generate": f"nouvelle : {kp['private_key_path']}",
                                  "file": f"{kp['public_key_path']}",
                                  "existing": f"existante sur le cloud : {kp['name']}"}[kp["mode"]])
    proxy = answers.get("internet_proxy")
    for vm in answers.get("instances") or []:
        extra = " + IP publique" if vm["floating_ip"] else ""
        if vm.get("role") == "bastion":
            extra += " (bastion : porte d'entrée SSH)"
        if proxy and vm["name"] == proxy["bastion"]:
            extra += " + proxy pour les autres"
        elif proxy and not vm["floating_ip"]:
            extra += " (Internet via proxy)"
        elif not vm["floating_ip"]:
            extra += " (sans Internet)"
        extra += " + nginx" if vm["nginx"] else ""
        table.add_row("Machine", f"{vm['name']} · {vm['flavor']} · {vm['image']}{extra}")
    for vol in answers.get("volumes") or []:
        where = f" → {vol['attach_to']}" if vol["attach_to"] else " (non attaché)"
        table.add_row("Volume", f"{vol['name']} · {vol['size']} Go {vol['type']}{where}")
    ui.console.print()
    ui.console.print(table)


def run():
    """Pose toutes les questions et retourne le dictionnaire de réponses."""
    ui.title("Nouveau projet", "Réponds aux questions : felcloud écrit le code pour toi")
    project, tool = ask_project()
    cloud_name = ask_cloud()

    with ui.console.status(f"Lecture des ressources disponibles sur « {cloud_name} »..."):
        try:
            conn = cloud.connect(cloud_name)
            conn.authorize()
            found = cloud.discover(conn)
        except Exception as exc:
            raise ui.Abort(f"Connexion impossible : {cloud.explain(exc)}") from exc
    ui.ok(f"{len(found.images)} images et {len(found.flavors)} tailles disponibles")

    bricks = ask_bricks()
    want_fip = "floating_ip" in bricks
    if want_fip and "instances" not in bricks:
        ui.warn("Une IP publique s'attache à une machine : j'ajoute « Machines virtuelles ».")
        bricks.append("instances")

    answers = {"version": 1, "project": project, "tool": tool, "cloud": cloud_name}
    if "network" in bricks or "instances" in bricks:
        if "network" not in bricks and "instances" in bricks:
            ui.info("Les machines ont besoin d'un réseau.")
        answers["network"] = ask_network(project, found, needs_internet=want_fip)
    if "security_group" in bricks:
        answers["security_group"] = ask_security_group()
    if "keypair" in bricks:
        answers["keypair"] = ask_keypair(project, found)
    if "instances" in bricks:
        if "keypair" not in bricks:
            ui.warn("Sans clé SSH, tu ne pourras pas te connecter aux machines.")
        answers["instances"], answers["internet_proxy"] = ask_instances(project, found, want_fip)
    if "volumes" in bricks:
        workloads = [vm for vm in answers.get("instances") or [] if vm.get("role") != "bastion"]
        answers["volumes"] = ask_volumes(project, found, workloads)

    summary(answers)
    if not check_quotas(answers, found):
        if not ui.confirm("Générer quand même le projet ?", default=False):
            raise ui.Abort("Génération annulée.")
    if not ui.confirm("Générer le projet ?", default=True):
        raise ui.Abort("Génération annulée.")
    return answers
