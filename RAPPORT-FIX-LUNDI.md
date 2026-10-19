# Correctifs LUNDI — 2026-10-19

Périmètre : cartes L1 à L7. Carte L2 non touchée (voir plus bas). Aucun secret généré,
aucune stack démarrée, aucune attaque lancée, historique git non réécrit.

## Fait

| # | Tâche | Commit | Fichiers touchés |
|---|---|---|---|
| 1 | `.gitignore` couvre `.secrets/` | `9bc940a` | `.gitignore` |
| 2 | Scaffold mort purgé (4 ensembles, 7 fichiers) | aucun, voir note | suppressions de fichiers non suivis |
| 3 | L1 : spec `payment` alignée sur le code (route `/payments` conservée) | `f5fd915` | `docs/openapi/payment.json` |
| 4 | L4 : cible paramétrable et bornée, scénario documenté | `9dfd702` | `scripts/attack_lab.py`, `docs/04-ATTAQUE.md` (nouveau), `docs/INSTALL.md`, `tests/test_configs.py` |
| 5 | L5 : chaîne baseline → entraînement exécutable, choix du modèle documenté | `203eb74` | `services/detector/collect_baseline.py` (nouveau), `train.py`, `model.py`, `docs/05-ML-RAG.md`, `docs/INSTALL.md`, `.gitignore`, `tests/test_baseline_chain.py` (nouveau) |
| 6 | L6 : les 3 autres specs alignées sur le code | `a08251d` | `docs/openapi/auth.json`, `remediator.json`, `rag.json`, `docs/03-INTERFACES.md` |
| 7 | L7 : script de vérification du jalon | `3b03771` | `scripts/check_lundi.py` (nouveau), `tests/test_check_lundi.py` (nouveau), `README.md` |

Détail par tâche, ce qui n'est pas évident :

- **1.** Aucun secret n'était suivi par git (`git ls-files` vide) et aucun `.gitkeep` ne force
  le suivi. `git check-ignore -v .secrets/runtime/test` renvoie la règle.
- **2.** Supprimés après vérification des références : `docker-compose.yml`, `ansible/`,
  `services/orchestrator/`, `docs/API-CONTRACTS.md`. Seule référence trouvée : le libellé de
  la carte L3 dans `trello-snapshot.json` (un titre, pas un chemin). Le `docs/` est monté dans
  le RAG qui indexe tous les `*.md` : l'ancien `API-CONTRACTS.md` décrivait un orchestrateur et
  une recréation de conteneur inexistants, donc l'assistant pouvait répondre à partir d'une
  doc fausse. Résultat : un seul Compose, un seul dossier Ansible, un seul remédiateur, une
  seule source pour les contrats. **Pas de commit** : ces fichiers n'avaient jamais été suivis.
- **3.** `/pay` n'apparaît plus nulle part (hors Trello). `/health` est sans authentification et
  ne touche pas la base ; c'est `/ready` qui lit la base. `/health` n'est pas publié par le WAF
  (accès interne), ce qui est documenté dans la spec.
- **4.** La cible reste bornée au lab : `--target` ou `LAB_TARGET` n'acceptent qu'une IP
  littérale de `192.168.137.0/24` ou loopback, tout autre hôte est refusé avant connexion. Le
  commentaire d'origine montrait que la cible figée était un garde-fou voulu ; je l'ai gardé
  sous une autre forme au lieu de le supprimer. `--lab-authorized` était déjà obligatoire.
  Le script reste autonome (il est copié seul sur le PC Attaquant).
- **5.** Changement de comportement à connaître : `python -m services.detector.train` ne collecte
  plus lui-même, il lit `/models/baseline.json`. La collecte est dans
  `python -m services.detector.collect_baseline`. L'intérêt : réentraîner sur le même jeu de
  données pour calibrer le seuil (carte M5) sans recollecter 3 minutes. `train_model` et
  `score` sont inchangés, le modèle reste OneClassSVM.
- **6.** Vérifié en exécutant les trois applications FastAPI en mémoire (secrets factices en
  dossier temporaire, sans réseau, sans Ansible) : chaque statut HTTP observé est déclaré dans
  la spec, routes et schémas de requête identiques au code. Jeton déclaré HMAC maison
  (`http`/`bearer`), jamais JWT.
- **7.** `payment` et `prometheus` ne publient aucun port sur l'hôte ; le script les interroge
  avec `docker compose exec` (GET uniquement, sous-commandes `ps` et `exec` seulement, vérifié
  par un test sur le source).

Tests exécutés (venv jetable hors dépôt) : `test_configs` 5/5, `test_baseline_chain` 5/5,
`test_check_lundi` 10/10, `test_ml_rag` 2/3 (échec préexistant, voir plus bas). **Je n'ai pas
lancé la suite complète** (`test_api`, `test_alerts`, `test_ledger`, `test_native_chain` : ce
dernier démarre des serveurs et Ansible) ; à faire dans WSL.

## Non fait et pourquoi

- **Commit de la tâche 2** : suppressions de fichiers non suivis, rien à commiter.
- **Aucune exécution réelle de `check_lundi.py`, `collect_baseline`, `train`, `attack_lab`** :
  garde-fou n°3. Leur logique est testée avec des simulations, pas contre la vraie stack.
- **Non vérifié par exécution** dans les specs : le service `rag` (importe LangChain et
  construit son corpus), les trois variantes de 202 de `/alerts` (une alerte valide lancerait
  Ansible), le 503 de `/payments` (couvert par `tests/test_api.py` que je n'ai pas lancé),
  le 500 de `/ready` quand la base est injoignable. Ces points sont décrits d'après le code.
- **Hypothèses de `check_lundi.py` non confirmées sur une vraie stack** : `wget` présent dans
  l'image Prometheus, et l'endpoint `GET /api/datasources/uid/<uid>/health` de Grafana 11.6.
  Si l'un manque, l'étape concernée affiche un ECHEC avec sa raison, pas un faux succès.
- **Carte L2** : non touchée. Je n'ai rien constaté de contraire à l'audit, mais je ne l'ai pas
  réexaminée.

## Décisions qui ne m'appartiennent pas

1. **Disposition du dépôt.** Git suit encore `Workshop2026-M2-GX/...` (import du 19/10), alors
   que le working tree a les mêmes fichiers à la racine (affichés ` D` puis `??`). Mes 6 commits
   ont ajouté **uniquement les fichiers que j'ai modifiés** à la racine : `HEAD` contient donc
   désormais deux versions de certains fichiers (ex. `docs/INSTALL.md`), et la plupart des
   fichiers racine restent non suivis. À trancher avant de construire le ZIP : valider le
   déplacement complet (après relecture) ou revenir au dossier `Workshop2026-M2-GX/`.
2. **`.env.example`** est un reste de mon ancien scaffold (JWT_SECRET, POSTGRES_PASSWORD,
   ORCHESTRATOR_TOKEN) et contredit la conception : `.env` ne doit contenir que de la
   configuration non secrète (`LAB_BIND`, `OLLAMA_URL`), les secrets vont dans `.secrets/`.
   Il n'était pas dans la liste de la tâche 2, je ne l'ai pas supprimé. Recommandation : le
   remplacer par un modèle qui ne contient que ces deux variables.
3. **Plan et Trello à réaligner sur le code** (cartes à renommer par un humain) :
   `/pay` → `/payments` (L1), `docker-compose.yml` → `compose.yaml` (L3),
   IsolationForest → OneClassSVM (L5, décision D-07 documentée), « Auth JWT » → jeton HMAC
   maison (M1), « endpoint `/anomaly` » → état exposé par `/ops/ml` (M5).
4. **Budget de connexion de `/auth/token`** : 30 tentatives par minute et par adresse source
   vue par le service. Derrière le WAF et l'edge, aucun `X-Forwarded-For` n'est approuvé, donc
   cette adresse est probablement celle du proxy et le budget est partagé par tous les clients,
   y compris la connexion que fait le remédiateur pour vérifier la reprise. Déduit de la
   configuration, pas observé. Si un attaquant épuise ce budget pendant l'incident, la vérification
   peut échouer (`failed`, `manual_review_required`). À confirmer en exécution, hors périmètre lundi.
5. **Constantes de périmètre dupliquées** : `attack_lab.py` (autonome, copié seul sur le PC
   Attaquant) et `lab_client.py` (`ALLOWED`, utilisé par l'observateur) portent chacun leur liste
   de cibles autorisées. Je n'ai pas fusionné pour ne pas rendre `attack_lab.py` dépendant du
   dépôt.
6. **Taux de faux positifs** : sur la fixture synthétique (90 points, graine 3), 3 points normaux
   sur 18 sortent de la frontière avec `nu=0.03` (environ 17 %). Mesure sur données
   synthétiques uniquement, consignée dans `docs/05-ML-RAG.md`. À remesurer sur la vraie baseline.

Hors périmètre, constaté, non corrigé : `tests/test_ml_rag.py::test_document_retrieval_is_grounded`
échoue sur cet hôte Windows. Le test écrit un fichier avec l'encodage par défaut de Windows
(cp1252) que `Corpus` relit en UTF-8. Cause identifiée, non vérifié sous WSL/Linux. (Carte W5.)

## Incidents

Aucun. Aucun secret n'est suivi par git (`git ls-files` vérifié après les 6 commits), aucun
`.secrets/`, `.env` ou `*.key` n'existe dans le dépôt.

Transparence : pour vérifier les specs, j'ai exécuté le code des services en mémoire
(`TestClient`, secrets factices dans un dossier temporaire, sans réseau ni sous-processus).
Ce n'est ni un script de `scripts/` ni le démarrage de la stack, mais c'est plus que de la
lecture seule. Les dépendances ont été installées dans un venv jetable en dehors du dépôt ;
`pytest` et `pyyaml` sans version épinglée, les autres aux versions de `requirements.txt`.
Les trois dossiers `__pycache__` créés par ma première tentative d'import ont été supprimés.

## Reste à faire par un humain

Dans cet ordre, depuis WSL à la racine du dépôt :

1. Trancher la disposition du dépôt (décision 1) avant toute construction du ZIP.
2. `python scripts/init_secrets.py` (age et sops installés). `.secrets/` est désormais ignoré.
3. `docker compose up -d --build`. Le `--build` est nécessaire : l'image embarque le code du
   détecteur modifié.
4. `python scripts/check_lundi.py` : clôt la partie technique du jalon L7. Lire les ECHEC
   éventuels, notamment `wget` dans Prometheus et l'endpoint de santé de la datasource Grafana.
5. Baseline et modèle : `python scripts/normal_traffic.py --seconds 240`, puis dans un second
   terminal `docker compose exec detector python -m services.detector.collect_baseline` suivi de
   `docker compose exec detector python -m services.detector.train`. Aucune attaque pendant ce temps.
6. `python -m pytest -q` en entier (non lancé par moi).
7. Validation humaine : les 4 contrats par les 6, le scénario d'attaque par l'équipe et le coach
   (carte L4), et la mise à jour des cartes Trello (décision 3).
