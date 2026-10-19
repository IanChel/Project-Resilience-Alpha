# Correctifs LUNDI — Project Resilience Alpha

Prompt à donner à l'agent VS Code, à la racine du dépôt :

> Lis `FIX-LUNDI.md` et exécute les tâches dans l'ordre.

**Périmètre : uniquement les cartes LUNDI (L1 → L7) du tableau Trello**
(`trello-snapshot.json`). Tu ne touches à rien qui relève de mardi, mercredi,
jeudi ou vendredi. Si tu vois un problème hors périmètre, tu le notes dans le
rapport final, tu ne le corriges pas.

**Carte L2 (projet React + Tailwind) : rien à faire.** L'audit la donne complète
et sans écart. Si tu constates le contraire en travaillant, signale-le dans le
rapport final — ne corrige pas de ton propre chef.

**Ordre d'exécution :** la tâche 1 d'abord, sans exception. Les tâches 2 à 7
peuvent se faire dans n'importe quel ordre.

---

## 0. Garde-fous

Ces règles priment sur toutes les tâches ci-dessous.

1. **Tu ne réécris jamais l'historique git.** Pas de `rebase -i`, pas de
   `filter-branch`, pas de `force-push`. Si un fichier doit disparaître, tu le
   supprimes du working tree et tu commites normalement.
2. **Tu ne commites aucun secret, et tu ne génères aucun secret.**
   `scripts/init_secrets.py` ne doit **pas** être lancé par toi — c'est une
   action humaine, après le correctif `.gitignore` de la tâche 1.
3. **Tu ne lances pas l'attaque DoS**, tu ne démarres pas la stack, tu n'exécutes
   aucun script de `scripts/` autre que les linters/tests déjà configurés.
4. **Avant toute suppression de fichier**, tu vérifies qu'il n'est référencé
   nulle part (`grep -rn "<nom>" . --exclude-dir={.git,node_modules}`) et tu
   listes ce que tu comptes supprimer **dans ta réponse, avant de le faire**.
   Si un doute subsiste, tu ne supprimes pas : tu signales.
5. **Tu ne renommes pas du code qui fonctionne** pour le faire coller à un
   libellé de carte. Quand le code et le plan divergent et que le code est
   meilleur, c'est le plan et la doc qu'on aligne — pas l'inverse.
6. Un commit par tâche, message clair en français, préfixé `fix(lundi):` ou
   `docs(lundi):`.

---

## 1. `.gitignore` ne couvre pas `.secrets/` — **à faire en premier**

**Pourquoi d'abord :** dès que quelqu'un lance `scripts/init_secrets.py`,
`.secrets/runtime/*` contiendra des mots de passe en clair. Si `.gitignore` ne
les couvre pas à ce moment-là, ils partent au prochain `git add .`. Ce correctif
doit être en place **avant** que la stack soit initialisée.

**À faire :**
- Ajouter à la racine du `.gitignore` : `.secrets/`, `*.key`, `*.pem`, `.env`,
  `.env.*` (en gardant `!.env.example` s'il existe).
- Vérifier qu'aucun de ces chemins n'est **déjà** suivi par git :
  `git ls-files | grep -E '^\.secrets/|\.env$|\.key$|\.pem$'`.
  Si la commande renvoie quelque chose : **tu ne supprimes rien toi-même**, tu
  le signales en tête de ton rapport comme incident à traiter manuellement.
- Vérifier qu'un `.secrets/.gitkeep` ou équivalent ne force pas le suivi du
  dossier.

**Fini quand :** `git check-ignore -v .secrets/runtime/test` renvoie bien la
règle du `.gitignore`, et `git ls-files` ne contient aucun secret.

---

## 2. Purger le scaffold mort (carte L3, et hygiène générale)

Le dépôt contient deux générations de fichiers qui se contredisent. Le risque
concret : quelqu'un corrige la mauvaise copie jeudi et perd une demi-journée.

| Fichier mort (scaffold) | Remplacé par (réel) |
|---|---|
| `docker-compose.yml` | `compose.yaml` |
| `ansible/remediate_dos.yml` | `infra/ansible/contain.yml` |
| `services/orchestrator/` | `services/remediator/` |
| `docs/API-CONTRACTS.md` | `docs/openapi/` + `docs/03-INTERFACES.md` |

**À faire :**
- Pour **chacun**, appliquer le garde-fou n°4 : chercher toutes les références
  (imports Python, `services:` dans compose, chemins dans la CI, liens dans les
  `.md`, `COPY` dans les Dockerfile).
- Ne supprimer que ceux dont **zéro référence vivante** subsiste.
- Pour ceux qui sont encore référencés : ne pas supprimer, lister dans le rapport
  quelle référence les retient.

**Attention :** `docker-compose.yml` et `compose.yaml` sont tous deux des noms que
Docker Compose reconnaît. Tant que les deux coexistent, le comportement dépend de
la version de Compose installée sur chaque poste — deux membres du groupe peuvent
lancer deux stacks différentes sans s'en rendre compte. C'est la suppression la
plus urgente des quatre.

**Fini quand :** un seul fichier Compose à la racine, un seul dossier Ansible, un
seul service de remédiation, une seule source de vérité pour les contrats d'API.

---

## 3. Carte L1 — faire coïncider le contrat d'API et le code

**Constat de l'audit :** l'API expose `/payments`, la carte et le plan parlent de
`/pay`. Le code est correct (REST), c'est le libellé qui est approximatif.

**À faire :**
- **Ne pas renommer la route.** `/payments` reste.
- Vérifier que `docs/openapi/payment*.yaml` (ou équivalent) déclare bien
  `/payments` et `/health` avec les **vrais** schémas de requête/réponse du code.
- Vérifier que `/health` existe, ne demande pas d'authentification, et renvoie
  200 sans dépendre de la base (sinon ce n'est pas un healthcheck exploitable
  par le playbook de remédiation).
- Si une référence à `/pay` traîne dans le front, un script ou la doc, la
  corriger en `/payments`.

**Fini quand :** `grep -rn "/pay\b"` ne renvoie plus que des occurrences
légitimes, et la spec OpenAPI décrit exactement ce que le code sert.

---

## 4. Carte L4 — sortir l'IP en dur et documenter le scénario

**Constat :** `scripts/attack_lab.py` a `192.168.137.1` figé en dur, et le
scénario DoS n'est documenté nulle part.

**À faire :**
- Rendre la cible paramétrable : argument CLI `--target` **ou** variable
  d'environnement, avec `192.168.137.1` comme valeur par défaut. Rien ne doit
  casser pour qui lance le script sans argument.
- Vérifier que le garde-fou `--lab-authorized` est **obligatoire** : sans lui, le
  script doit refuser de démarrer avec un message explicite. S'il est optionnel,
  le rendre obligatoire.
- Créer ou compléter `docs/04-ATTAQUE.md` avec : le réseau `RESILIENCE-G6`,
  l'adresse de la cible, le scénario DoS retenu, ses bornes exactes (volume,
  débit, durée), la commande de lancement, et **la phrase qui dit que l'attaque
  ne s'exécute que sur le réseau de lab isolé**.

**Fini quand :** le scénario est lisible par quelqu'un qui n'a pas écrit le
script, et aucune IP n'est en dur dans le code.

---

## 5. Carte L5 — assumer le choix du modèle et préparer la baseline

**Constat :** le plan dit `IsolationForest`, le code utilise `OneClassSVM`. Par
ailleurs ni le jeu de baseline ni `model.joblib` n'existent — c'est normal, ce
sont des artefacts d'exécution, mais la chaîne qui les produit doit être prête.

**À faire :**
- **Ne pas changer de modèle.** Documenter le choix dans `docs/05-ML-RAG.md` :
  pourquoi `OneClassSVM` plutôt qu'`IsolationForest` sur ce jeu de données
  (volumétrie, nature des features, comportement sur une classe unique). Deux
  paragraphes suffisent, mais ils doivent tenir devant une question du jury.
- Vérifier que `services/detector/train.py` est exécutable de bout en bout :
  qu'il lit un fichier de baseline à un **chemin explicite et documenté**, et
  qu'il écrit `model.joblib` à un chemin tout aussi explicite.
- Vérifier qu'un script de **collecte** de baseline existe et écrit au chemin que
  `train.py` attend. S'il n'existe pas, le créer : il interroge les métriques
  Prometheus pendant N secondes de trafic normal et sérialise le résultat.
- Ajouter les artefacts (`*.joblib`, le dossier de baseline) au `.gitignore` —
  un modèle binaire n'a rien à faire dans le dépôt.
- Documenter la séquence exacte dans `docs/05-ML-RAG.md` :
  `collecte baseline → train.py → model.joblib → le détecteur sort de
  waiting_for_trained_model`.

**Tu n'entraînes pas le modèle toi-même** (garde-fou n°3). Tu rends la séquence
exécutable par un humain en une commande par étape.

**Fini quand :** quelqu'un qui découvre le dépôt peut entraîner le modèle en
suivant la doc, sans lire le code.

---

## 6. Carte L6 — vérifier que les 4 contrats décrivent le vrai code

**Constat :** les 4 specs existent (`auth`, `payment`, `rag`, `remediator`).
L'audit ne dit pas si elles sont **justes**. Un contrat faux est pire qu'un
contrat absent : les autres se branchent dessus et découvrent l'écart mardi.

**À faire :** pour chacune des 4 specs, comparer avec le code qui l'implémente :
- chaque chemin déclaré existe réellement dans le code, et réciproquement ;
- les méthodes HTTP correspondent ;
- les champs des schémas de requête et de réponse correspondent aux modèles
  Pydantic réels (noms **et** types) ;
- les codes de statut documentés sont ceux que le code renvoie vraiment,
  erreurs comprises ;
- le schéma de sécurité déclaré correspond au mécanisme réel — attention, le
  code utilise un **jeton HMAC signé maison**, pas un JWT standard. Si la spec
  annonce `bearerFormat: JWT`, c'est faux : corriger la spec, pas le code.

**Fini quand :** tu peux affirmer, ligne par ligne, que les 4 specs sont le
reflet du code. Tout écart que tu ne peux pas corriger sans décision d'équipe,
tu le listes.

---

## 7. Carte L7 — le script de vérification du jalon de lundi

**Constat :** le sync point de lundi (`la stack démarre + métriques visibles dans
Grafana + contrats validés`) n'est vérifiable qu'en exécution, et rien ne permet
de le vérifier autrement qu'à l'œil.

**À faire :** créer `scripts/check_lundi.py` (ou `.sh`), qui **vérifie sans rien
démarrer ni modifier** et sort en code 0 ou 1 :
1. les conteneurs attendus sont `Up` (db, payment, prometheus, grafana, loki) ;
2. `GET /health` du service paiement renvoie 200 ;
3. `GET /metrics` renvoie bien des séries applicatives ;
4. Prometheus a scrapé la cible — son endpoint `targets` la donne `up` ;
5. Grafana répond et sa datasource Prometheus est joignable.

Chaque étape affiche `OK` ou `ECHEC` avec la raison. Pas de sortie muette.

**Ce n'est pas `run-demo.sh`** (carte J3, jeudi, hors périmètre) : ici on
constate, on ne remet rien à zéro.

**Fini quand :** le script existe, est documenté en une ligne dans le README, et
un humain peut l'exécuter une fois la stack levée pour clore le jalon de lundi.

---

## 8. Rapport de sortie

Termine par `RAPPORT-FIX-LUNDI.md` :

```markdown
# Correctifs LUNDI — <date>

## Fait
| # | Tâche | Commits | Fichiers touchés |

## Non fait et pourquoi
<Ce que tu n'as pas pu faire : référence vivante qui retient un fichier,
décision d'équipe nécessaire, information manquante.>

## Décisions qui ne t'appartiennent pas
<Tout écart plan/code que tu as documenté sans trancher.>

## Incidents
<En particulier : secret déjà suivi par git, s'il y en a un.>

## Reste à faire par un humain
<Les actions runtime : init_secrets.py, docker compose up, collecte baseline,
entraînement du modèle, exécution de check_lundi.py.>
```

Puis, en trois lignes maximum dans ta réponse : ce qui est débloqué, ce qui
reste bloquant pour le jalon de lundi, et ce qu'un humain doit lancer maintenant.
