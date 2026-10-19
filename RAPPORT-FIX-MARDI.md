# Correctifs MARDI — 2026-10-19

Périmètre : tâche 1 (clôture de lundi) puis cartes M1 à M7. Aucun secret généré, aucune stack
démarrée, aucune attaque lancée, aucune calibration ni collecte ni entraînement lancés, historique
git non réécrit. Rien de mercredi à vendredi n'a été touché.

## Fait

| # | Tâche | Commit | Fichiers touchés |
|---|---|---|---|
| 1 | Clôture de lundi : **déjà faite par IanChel** (`9aef239`), vérifiée | aucun | aucun |
| 2 | `.env.example` réduit à la configuration non secrète lue | `ff16f1b` | `.env.example` |
| 3 | M5 : `GET /anomaly` | `d4bfed5` | `services/detector/main.py`, `model.py`, `docs/openapi/detector.json` (nouveau), `docs/03-INTERFACES.md`, `tests/test_anomaly_endpoint.py` (nouveau) |
| 4 | M5 : calibration, `nu` et `consecutive` configurables | `b172c5a` | `services/detector/model.py`, `main.py`, `train.py`, `window.py` (nouveau), `scripts/calibrate_detector.py` (nouveau), `compose.yaml`, `.env.example`, `docs/05-ML-RAG.md`, `tests/test_calibration.py` (nouveau), `tests/test_anomaly_endpoint.py` |
| 5 | M1 : budget de connexion de `/auth/token` | `5932652` | `services/remediator/main.py`, `tests/test_login_budget.py` (nouveau), `docs/06-SECURITE.md` |
| 6 | M2, M3, M4 : vérification (voir section dédiée) | aucun | aucun, pas de réécriture demandée |
| 7 | M6 : audit des documents de gouvernance | `45873ed` | `docs/06-SECURITE.md`, `07-GOUVERNANCE.md`, `08-PCA-PRA.md` |
| 8 | M7 : script de preuve du jalon | `6cc0153` | `scripts/check_mardi.py` (nouveau), `services/detector/window.py`, `tests/test_check_mardi.py` (nouveau), `tests/test_window_report.py` (nouveau), `docs/05-ML-RAG.md`, `README.md` |

Ce qui n'est pas évident, tâche par tâche :

- **1.** Le commit `9aef239` (« Fix tâches Lundi », IanChel) a déjà déplacé `Workshop2026-M2-GX/*` à la
  racine par renommage. Je n'ai fait que vérifier chaque critère : `git ls-files | sed … | uniq -d` vide,
  aucun secret ni artefact suivi, 95 fichiers suivis, `git status` propre, aucun dossier `Workshop2026-M2-GX`.
  Un `git clone` dans un dossier vierge donne 95 fichiers, statut propre, identique au working tree.
  Seul `Fix à faire/FIX-MARDI.md` reste non suivi (c'est ce fichier d'instructions).
- **2.** Seules deux variables sont réellement lues depuis `.env` (interpolation Compose) : `LAB_BIND` et
  `OLLAMA_URL`. J'ai ensuite ajouté `DETECTOR_CONSECUTIVE` et `DETECTOR_NU` (tâche 4), lues par
  `model.py` via `compose.yaml`. Aucune n'est un secret. `GRAFANA_PASSWORD` (lu par `check_lundi.py`) et
  `LAB_TARGET` (lu par le script autonome du PC Attaquant) n'y figurent pas : un secret, et un script qui ne
  charge pas `.env`.
- **3.** Le verdict décrit **l'observation courante** : `status == monitoring` ET score négatif ET rejets de
  capacité. C'est la règle exacte du compteur d'alerte, extraite en une fonction (`is_anomalous`) que la boucle
  et `/anomaly` partagent. Il ne pouvait pas s'appuyer sur le compteur, remis à zéro dans la même itération
  que l'envoi de l'alerte. Il se déduit de l'état existant : `/ops/ml` est strictement inchangé. Sans modèle
  ou après une erreur de collecte : `anomaly=false`, `status` le dit, `score=null` (jamais un score périmé).
  Au repos le verdict est faux par construction, car il exige des rejets.
- **4.** `nu` : `train --nu` ou `DETECTOR_NU`, consigné dans `report.json`. `consecutive` :
  `DETECTOR_CONSECUTIVE`, lu au démarrage. Valeur invalide : arrêt avec message, jamais de repli silencieux.
  La règle de répétition est unique (`next_consecutive`, `alert_due`, `replay_alerts`). Pour récupérer les
  données réelles d'une attaque, le détecteur journalise déjà chaque observation : `window export` les relit
  a posteriori (heure sans fuseau refusée). `calibrate_detector.py` est hors ligne, entraîne des **candidats en
  mémoire** et n'écrit que son JSON de preuve. Voir « Décisions » pour mon interprétation de « ne réentraîne pas ».
- **5.** Le diagnostic de lundi **tient**, établi par le code et la topologie (`auth/main.py:19-23`,
  `remediator/main.py`, l'edge ne pose aucun `X-Forwarded-For`). Correction : le remédiateur obtient son jeton
  directement auprès d'`auth` par le réseau interne `app` (`AUTH_URL`), donc avec son propre budget. Le
  rate-limit public est conservé, la preuve métier passe toujours par le WAF. Le test épuise le budget public
  et vérifie que `business_verify` aboutit ; un second rejoue l'ancien couplage et constate le 429.
- **7.** Aucun terme périmé dans 06, 07, 08. Cinq phrases inexactes corrigées (détail plus bas).
- **8.** L'analyse tourne dans le conteneur du détecteur pour réutiliser `is_anomalous` (nouvelle
  sous-commande `window report`, appelée par `docker compose exec`, GET uniquement). La preuve est écrite
  même en cas d'échec (`passed: false`).

Tests exécutés (venv jetable hors dépôt) : **104 passent sur 105**. Seul échec : le test d'encodage Windows de
`test_ml_rag` (préexistant, carte W5). Cela inclut `test_api`, `test_alerts` et `test_ledger`, que je
n'avais pas lancés lundi, sur SQLite et sous Windows. **Non exécuté** : `test_native_chain` (démarre uvicorn et Ansible,
impossible ici) et tout test contre PostgreSQL.

## Vérification de M2, M3, M4 (tâche 6)

| Carte | Point | Verdict | Fichier et ligne |
|---|---|---|---|
| M2 | Aucun mock actif dans le chemin de paiement | CONFIRMÉ | aucune occurrence de `mock` dans `frontend/`, `services/`, `infra/` |
| M2 | L'appel va sur `/payments` | CONFIRMÉ | `frontend/src/main.jsx:12` (`/api/payments`, routé vers `/payments` par `infra/nginx/default.conf:10`) |
| M2 | Un 503 affiche quelque chose d'utile | CONFIRMÉ | `main.jsx:8` construit `503 — Simulated downstream capacity exhausted`, affiché dans le bandeau `role="alert"` |
| M2 | Réponse non JSON (502/504 HTML de l'edge, page 403 du WAF) | **ÉCART** | `main.jsx:8` : `await r.json()` non protégé, l'utilisateur lit une erreur d'analyse JSON au lieu du statut |
| M2 | Bandeau d'erreur après reprise | **ÉCART** | `main.jsx:11` : un échec du rafraîchissement pose l'erreur, aucun succès ne l'efface (seuls `:10` et `:12` font `E('')`) ; le bandeau rouge peut rester affiché après la reprise |
| M3 | Playbooks valides syntaxiquement | **NON VÉRIFIÉ** | `ansible-core` ne s'importe pas sous Windows (module POSIX `grp`) : pas de vrai `--syntax-check`. Vérification statique seulement : YAML, structure, modules en FQCN, analyse Jinja de chaque expression, pour `contain.yml` et `deploy.yml` |
| M3 | Exécutables seuls | CONFIRMÉ (lecture) | `contain.yml:10,13,21` : valeurs par défaut pour `PAYMENT_URL`/`SECRETS_DIR`, aucune variable à fournir ; `deploy.yml` s'appuie sur `playbook_dir` |
| M3 | Séries déclarées et scrapées | CONFIRMÉ | `services/payment/main.py:14-18` ; `infra/prometheus/prometheus.yml:5-7` (job `payment`, `/metrics`) |
| M3 | Série `quotes/200` présente dès le démarrage | **ÉCART** | `payment/main.py:87` : `REQUESTS.labels('quotes','200')` n'est créée qu'au **premier devis accepté**. Avant, la requête du détecteur (`telemetry.py:7`) est vide et il lève `Prometheus series not ready` (`telemetry.py:20`) : `telemetry_or_delivery_error`. Touche directement M7 |
| M4 | Aucune part d'aléatoire non graînée | CONFIRMÉ | `scripts/attack_lab.py` n'utilise ni `random`, ni `uuid`, ni `secrets` ; charge fixe `{"amount_cents":100}` |
| M4 | Même charge à paramètres égaux | CONFIRMÉ avec réserve | `attack_lab.py:44-47` : au plus 20 req/s, 12 en vol. Le **volume offert** est identique, pas les **comptes** exacts : ils dépendent de l'ordonnancement et de la latence du serveur |
| M4 | « Deux lancements successifs, même effet » | **ÉCART (précondition)** | le confinement est persisté (`payment/main.py:27` le recharge, `:92-98` l'écrit) : un 2e lancement sans réinitialisation ne produit plus de 503. Reset à la main, documenté dans `docs/09-RECETTE-RENDU.md:35-39` ; `run-demo.sh` n'existe pas (carte J3) |

## Non fait et pourquoi

- **Aucune exécution réelle** de `calibrate_detector.py`, `window export/report`, `check_mardi.py`,
  `collect_baseline`, `train` : garde-fou n°3. Leur logique est testée avec des données synthétiques et
  docker/Prometheus simulés. Les chemins de `docker compose exec` et l'accès à Prometheus depuis le conteneur
  du détecteur sont déduits de `compose.yaml`, pas observés.
- **`ansible-playbook --syntax-check` réel** : impossible sous Windows (voir M3). À lancer sous Linux :
  `ansible-playbook -i localhost, infra/ansible/contain.yml --syntax-check` (idem `deploy.yml`).
  Je n'ai pas démarré de conteneur Docker pour le contourner.
- **M2, M3, M4 non corrigés** : la consigne est de vérifier, pas de réécrire. Les quatre ÉCARTS sont listés.
- **Gouvernance 07 et 08** : analyse de risques, notes de gravité, RTO/RPO, rôles A à E, contenu NIS2/DORA et
  dates réglementaires non vérifiés ni modifiés (hors périmètre de code).

## Décisions qui ne m'appartiennent pas

1. **Publier `/anomaly` à l'edge ?** Je l'ai laissée interne : élargir la surface publique est une décision de
   sécurité. Pour la montrer au jury, comme `/ops/ml` :
   `location = /ops/anomaly { auth_request /_operator; proxy_pass http://detector:8000/anomaly; }`
   dans `infra/nginx/default.conf`, puis mettre à jour `docs/03-INTERFACES.md` (colonne Publication).
2. **Pré-créer la série `quotes/200`** (ÉCART M3). Une ligne au démarrage de `payment` supprime
   l'état `telemetry_or_delivery_error` au repos ; sans elle, `check_mardi.py` étapes 1 et 2 échouent tant
   qu'aucun devis n'a été émis. Non faite (pas de réécriture), mais c'est le premier correctif que je
   recommande avant M7.
3. **Critère de la calibration.** « Zéro faux positif » est ambigu. La barrière « rejets de capacité > 0 »
   rend les fausses alertes de la règle complète nulles au repos, donc inutilisables pour départager
   `consecutive=1` de `5`. J'ai retenu comme critère FPruns (séries de `N` scores négatifs **sans** la barrière) ;
   FPgate (règle réelle) est affiché à côté. Si FPruns et la détection en moins de 10 s sont incompatibles,
   l'outil l'écrit (`NO PAIR`) avec les deux compromis sans trancher : c'est un arbitrage d'équipe.
4. **« Ne réentraîne pas ».** Pour balayer `nu` il faut ajuster un modèle par valeur. J'ai interprété la consigne
   comme : aucun modèle déployé n'est remplacé, ni aucune configuration modifiée. Les candidats vivent en mémoire.
5. **Une erreur de configuration arrête le détecteur.** Un `DETECTOR_CONSECUTIVE` invalide dans `.env` fait
   échouer le démarrage ; avec `restart: unless-stopped` le conteneur redémarre en boucle, le ML est aveugle
   et c'est visible dans ses journaux. C'est voulu (pas de repli silencieux), à accepter ou non.
6. **Risques résiduels de la tâche 5** (consignés dans `docs/06-SECURITE.md`) : un attaquant peut toujours
   verrouiller la **connexion publique** des opérateurs ; le remédiateur se connecte avec le compte `alice` et
   détient `session_key` (une identité de service dédiée serait plus propre, non faite car elle touche
   l'authentification et le registre). Se connecter au tableau de bord **avant** la démonstration.
7. **Gouvernance, à réévaluer par P6** : j'ai corrigé deux cellules du tableau de risques de `07`
   (« backup chiffré » alors que `backup.py` ne chiffre pas ; « aucune clé d'action » du RAG alors qu'il
   détient `session_key`, clé symétrique). Je n'ai pas touché aux cotations, qui pourraient changer.
8. **Plan et Trello** : « Auth JWT » (M1) reste un jeton HMAC maison ; les cartes renommées lundi sont à
   aligner par un humain.
9. **`08-PCA-PRA.md:16`** dit de rejouer une demande incertaine avec sa clé d'idempotence, alors que
   l'interface crée une clé par clic (`03-INTERFACES.md`). Laissé : c'est une consigne d'exploitation.

## Incidents

Aucun incident de sécurité : aucun secret suivi par git, aucun artefact dans le dépôt (vérifié).

Transparence :
- **Un `rm -rf` préventif de ma part a été bloqué** par le contrôle de sécurité (cible en variable, sur un dossier
  de clone scratch qui n'existait même pas encore). Je ne l'ai pas contourné ni rejoué : j'ai cloné dans un dossier
  de nom neuf, sans suppression. Rien n'a été supprimé.
- J'ai exécuté le code des services en mémoire (`TestClient`, secrets factices en dossier temporaire, sans réseau
  ni sous-processus) et lancé la suite de tests. Ce n'est ni un script de `scripts/` ni le démarrage de la stack.
- Dans un venv jetable **hors du dépôt** : `fastapi`, `httpx`, `prometheus-client`, `numpy`, `scikit-learn`, `joblib`
  aux versions de `requirements.txt`, `pytest` et `pyyaml` sans version épinglée, `ansible-core==2.18.4`
  (installé, inutilisable sous Windows). Seules commandes Docker/WSL : `docker --version` et `wsl.exe -l -v`.

## Reste à faire par un humain

Dans cet ordre, depuis WSL à la racine du dépôt :

1. Décider la pré-création de la série `quotes/200` (décision 2) ; sinon émettre un devis avant tout contrôle.
2. `python scripts/init_secrets.py` si ce n'est pas fait, puis `docker compose up -d --build` (le `--build`
   est nécessaire : l'image embarque le code du détecteur et du remédiateur modifié).
3. `python scripts/check_lundi.py` (jalon de lundi, jamais exécuté).
4. Baseline puis modèle : `normal_traffic.py`, `collect_baseline`, `train` (docs/05-ML-RAG.md).
5. **Jalon M7** : attaque depuis le PC Attaquant, puis `python scripts/check_mardi.py --last 120`. Garder le
   fichier `runtime/evidence/m7-proof-*.json`. Refaire devant les six.
6. Si faux positifs ou délai trop long : exporter les fenêtres et lancer `scripts/calibrate_detector.py`
   (docs/05-ML-RAG.md, section Calibration). Appliquer le couple choisi dans `.env`.
7. Entre deux attaques, réinitialiser le confinement (`docs/09-RECETTE-RENDU.md`, « Reset entre essais »).
8. Sous Linux : `python -m pytest -q` **en entier**, dont `test_native_chain` et les tests du registre sur
   PostgreSQL ; et `ansible-playbook … --syntax-check`.
9. Validation humaine : les cinq contrats, la décision 1, la relecture de `06`, `07`, `08` par P6.

## Prêt pour M7 ?

Conditions du jalon (carte M7 et `FIX-MARDI.md`) :

| Condition | État | Ce qui manque |
|---|---|---|
| L'attaque est lancée depuis le PC Attaquant | **EN ATTENTE D'EXÉCUTION** | Script prêt, borné et testé ; nécessite le point d'accès, `LAB_BIND`, le mot de passe `loadbot` |
| Un modèle entraîné est chargé | **BLOQUÉ** | Baseline et `model.joblib` sont des artefacts d'exécution absents ; secrets et stack jamais démarrés |
| Le détecteur mesure au repos (pas d'erreur de collecte) | **BLOQUÉ** par l'ÉCART M3 | Série `quotes/200` créée seulement au premier devis ; décision 2 |
| Le pic est visible dans Grafana et mesuré | **EN ATTENTE D'EXÉCUTION** | Le tableau de bord trace déjà `lab_capacity_denied_total` et `lab_active_work`, les séries que `check_mardi.py` mesure ; l'étape 3 est prête |
| `anomaly=true` sur le même événement | **EN ATTENTE D'EXÉCUTION** | Code prêt (`/anomaly`, `window report`, étape 4) ; dépend du modèle |
| `anomaly=false` au repos | **EN ATTENTE D'EXÉCUTION** | Faux par construction (la règle exige des rejets) si le détecteur mesure ; étape 2 prête |
| Aucun faux positif sur trafic normal soutenu | **EN ATTENTE D'EXÉCUTION** | Outil et cible prêts ; taux réel inconnu. Seule mesure : 3 points normaux sur 18 sous la frontière sur une **fixture synthétique**, protégés en pratique par la barrière de capacité |
| La vérification de reprise survit à un flot de connexions publiques | **SATISFAITE (code et test en mémoire)** | Budget de connexion découplé ; à confirmer en exécution et avec `test_native_chain`, non lancé ici |
| Démonstration refaite devant les six | **HUMAIN** | — |
| Répétabilité d'une 2e attaque | **EN ATTENTE** | Reset manuel du confinement entre essais |
