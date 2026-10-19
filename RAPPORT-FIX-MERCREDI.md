# Correctifs MERCREDI — 2026-10-19

Périmètre : cartes W1 à W7, précédées de la vérification de clôture de mardi et suivies de la régression complète.
Aucun secret généré, aucune stack démarrée, aucune attaque lancée, aucune calibration, collecte ni entraînement
lancés, historique git non réécrit. Rien de jeudi ni de vendredi n'a été touché.

## Clôture de mardi (tâche 1) : rien à traiter
Vérifié dans le dépôt, pas dans le rapport. `git status` propre, aucun doublon après retrait du préfixe
`Workshop2026-M2-GX/` ; `GET /anomaly` présent et documenté ; `nu` et `consecutive` réglables sans rebuild
(`compose.yaml`, `model.py`) ; `calibrate_detector.py` et `check_mardi.py` présents ; `.env.example` sans secret ;
`test_login_budget` prouve que la vérification du remédiateur survit à un budget public épuisé. Les tests de mardi relancés
(57, le sous-ensemble qui les prouve) passaient. Un commit humain (`92e08db`) n'a ajouté que le brief et le rapport de mardi.

**Point de mardi toujours ouvert, et qui pèse sur la journée** : la série `lab_requests_total{route="quotes"}` n'est
créée qu'au premier devis (`payment/main.py:87`), donc le détecteur reste aveugle au repos. Ce n'était pas dans le brief
de mercredi, je ne l'ai pas corrigé ; c'est le risque n°2 de `ETAT-SEMAINE.md`.

## Fait

| # | Tâche | Commit | Fichiers principaux |
|---|---|---|---|
| 1 | Clôture de mardi | aucun | vérification |
| 2 | W1 : ban d'IP, recréation écartée et documentée | `61d2a15` | `services/remediator/bans.py`, `services/detector/sources.py`, `infra/ansible/contain.yml`, `compose.ban.yaml`, `infra/waf/ra-ban.conf`, `docs/06-SECURITE.md` (déc. 1 et 2), `tests/test_ban.py` |
| 3 | W2 : chrono du dashboard | `61e73c0` | `services/remediator/main.py` (table `stages`), `frontend/src/chrono.js`, `Chrono.jsx`, `chrono.test.js`, `tests/test_incident_stages.py` |
| 4 | W3 : transaction témoin | `4038ff8` | `tests/test_witness.py` (code inchangé) |
| 5 | W4 : SIEM, secrets, débit | `b498a48` | `services/detector/soc.py`, `tests/test_soc_correlation.py`, `tests/test_secrets_hygiene.py`, `docs/06` |
| 6 | W5 : RAG | `9031ed7` | `tests/test_ml_rag.py`, `test_rag_corpus.py`, `test_rag_service.py`, `docs/05` (D-08), `requirements-dev.txt` |
| 7 | W6 : preuve de reprise | `c18fc33` | `scripts/acceptance.py`, `services/detector/main.py`, `tests/test_acceptance_evidence.py`, `docs/09` |
| 8 | W7 : preuve des 60 s | `03af62d` | `scripts/check_mercredi.py`, `tests/test_check_mercredi.py` |
| 9 | Régression et tableau de bord | `0c2c799`, `513c9b8`, `4f681ee` | `tests/test_repo_hygiene.py`, `tests/test_openapi_conformance.py`, `ETAT-SEMAINE.md`, `docs/06` (déc. 3) |

### 2c. Revalidation des 8 items de la checklist W1

| # | Item | Statut | Fichier et ligne |
|---|---|---|---|
| 1 | Détection ML branchée sur l'orchestrateur | FAIT | `detector/main.py:24,55,58` (alerte signée) → `remediator/main.py:123` |
| 2 | Orchestrateur déclenche Ansible | FAIT (RUNTIME en conteneur) | `remediator/main.py:84` ; jamais exécuté dans le conteneur |
| 3a | Playbook active le rate-limit | DIVERGENT ASSUMÉ | admission applicative `contain.yml:9`, `payment/main.py:92` ; aucune limite au WAF (`docs/06`, « Limitation de débit ») |
| 3b | Playbook bannit l'IP | RUNTIME | décision et playbook `contain.yml:26`, `remediator/bans.py:39` : FAIT et testé ; application au WAF `compose.ban.yaml:31` : non vérifiée |
| 4 | Recrée le conteneur | DIVERGENT ASSUMÉ | `docs/06-SECURITE.md:143`, décision 2 |
| 5 | Healthcheck valide le retour | FAIT | `contain.yml:43` + preuve métier `remediator/main.py:47` |
| 6 | Transaction témoin rejouée | FAIT | `remediator/main.py:47,58,96` ; 6 tests |
| 7 | Boucle sans intervention humaine | FAIT sur le chemin nominal (RUNTIME) | échec seul : `remediator/main.py:98` ; reprise après redémarrage `:110` |
| 8 | Chrono sous 60 s | RUNTIME | `scripts/check_mercredi.py:43`, `frontend/src/chrono.js:5` |

## Ce que j'ai trouvé en route (pas évident, et pas demandé)

- **Rien dans la stack n'enregistrait d'adresse source.** L'alerte ne pouvait donc pas porter l'IP à bannir, comme le brief
  le prévoyait ; seul le budget de connexion d'`auth` lit `request.client.host`, et c'est le proxy. J'ai complété le
  détecteur (adresse du **pair vu par le WAF**, jamais un en-tête), pas bricolé le playbook. Le brief disait « peu coûteux » :
  ce ne l'est pas, voir décision 1.
- **Le SOC ne corrélait rien** : quatre comptes isolés. Et ses signaux n'étaient visibles nulle part (le front ne lit pas
  `soc_signals`, Grafana filtrait sans `service="soc"`), alors que la doc disait qu'ils étaient exposés au dashboard.
- **Le RAG retrouvait la liste des questions de test au lieu des réponses** : `05-ML-RAG.md` les citait mot pour mot. Reformulé,
  et un test interdit l'auto-citation (je l'ai vérifié sur la version précédente). Le risque d'encodage du brief n'existait pas
  dans le code (`Corpus` lit déjà en UTF-8) : c'était le test qui était faux.
- **`requirements-dev.txt` n'installait pas LangChain** : les tests du RAG auraient échoué à l'import sur vos postes.
- **`scripts/package.py` aurait exclu `compose.ban.yaml`** de l'archive (liste blanche).
- **Un défaut de ma propre implémentation, corrigé** : à horodatage égal (résolution de ~15 ms sous Windows) l'ordre des
  étapes d'un incident dépendait de la base. Trouvé parce qu'un test échouait 1 fois sur 3.
- Mon `grep` en locale C **ne voyait pas** les mots accentués (« Recréer ») : tous les balayages de termes périmés ont été
  refaits en Python Unicode, et sont maintenant des tests.

## Résultats de la régression (tâche 9)

**9a. Suite complète, rien exclu : 24 fichiers, 244 réussis, 1 échec.**

| Fichier | OK | Fichier | OK |
|---|---|---|---|
| `test_acceptance_evidence` | 12 | `test_ml_rag` | 3 |
| `test_alerts` | 2 | `test_native_chain` | **0 sur 1** |
| `test_anomaly_endpoint` | 7 | `test_openapi_conformance` | 15 |
| `test_api` | 11 | `test_rag_corpus` | 10 |
| `test_ban` | 26 | `test_rag_service` | 15 |
| `test_baseline_chain` | 5 | `test_repo_hygiene` | 6 |
| `test_calibration` | 26 | `test_secrets_hygiene` | 7 |
| `test_check_lundi` | 10 | `test_soc_correlation` | 16 |
| `test_check_mardi` | 20 | `test_window_report` | 8 |
| `test_check_mercredi` | 19 | `test_witness` | 6 |
| `test_configs` | 5 | `test_incident_stages` (+ 12 tests Node) | 7 |
| `test_ledger` | 4 | `test_login_budget` | 4 |

**L'échec unique, `test_native_chain`, est un obstacle de plateforme, pas du code.** Il démarre de vrais serveurs puis exécute
Ansible, qui ne s'exécute pas sous Windows : deux blocages indépendants vérifiés (contrôle de locale `cp1252`, et le module
POSIX `grp` à l'import). Preuve que c'est bien l'étape Ansible : l'incident passe en `failed` 0,13 s après sa création.
**Rejoué avec un bouchon explicite à la place d'Ansible** (mêmes deux appels HTTP que `contain.yml`, copie temporaire du test
supprimée), toute la chaîne multi-processus passe en 18 s : inondation, 503, alerte signée, « playbook », vérification
métier par le proxy avec la connexion sur le chemin interne, registre à 200 000, paiement `200` sous charge. **Ce n'est pas
une preuve d'Ansible**, c'est celle de tout le reste. À passer sous Linux avec le vrai Ansible. Le registre n'a tourné que
sur SQLite.

**9b. Les vérifications des trois jours tiennent toujours**, et sont désormais des tests :
- aucun secret suivi, `.secrets/` ignoré, `.env.example` sans secret et lu (`test_repo_hygiene`, `test_secrets_hygiene`) ;
- aucun fichier du scaffold mort ; un seul Compose (plus la surcouche) et un seul dossier Ansible ;
- **les 5 specs décrivent toujours le code** : routes, codes **et corps** de vraies réponses validés contre leurs
  schémas. Mutation vérifiée : casser le type de `now` ou ajouter une propriété requise fait échouer le test avec un
  message précis ;
- aucune référence à orchestrateur, JWT, IsolationForest, `/pay`, `docker-compose.yml` dans le code ni la doc, sauf en
  négation ou dans une décision écrite (10 occurrences, toutes vérifiées).

**9c.** `ETAT-SEMAINE.md` : 21 lignes (L1 à W7), prêt pour le gel (non), risques par gravité, dette assumée avec le document
de justification de chaque écart.

## Non fait et pourquoi

- **Aucune exécution réelle** d'`acceptance.py`, `check_*`, `calibrate_detector.py`, de la collecte ou de l'entraînement :
  garde-fou n°3. Leur logique est testée contre un laboratoire simulé (horloge et serveur scriptés).
- **L'application du ban au WAF** n'est ni testée ni testable ici : trois hypothèses sur l'image `owasp/modsecurity-crs`
  (`ACCESSLOG`, chargement d'un fichier de règles monté, `SIGHUP` depuis un conteneur à capacité `KILL`), marquées `VERIFY`
  dans `compose.ban.yaml`. D'où une surcouche **optionnelle**, hors de la stack de base.
- **`ansible-playbook --syntax-check` réel** : impossible sous Windows.
- **Seuil de similarité du RAG (0,08)** : non modifié (le brief interdit de changer l'implémentation, et un seuil se règle
  sur plus de questions que celles que j'ai). Défaut mesuré et documenté, voir décisions.
- **Génération du RAG** : non vérifiée sans Ollama.
- **Deux écarts du front relevés mardi** (bandeau d'erreur jamais effacé, réponse non JSON) : hors du brief de mercredi.

## Décisions qui ne m'appartiennent pas

1. **Activer ou non le ban d'IP pour la soutenance.** Il est câblé de bout en bout et inerte par défaut. L'activer demande de
   passer la checklist de `docs/06-SECURITE.md` (décision 1) ; si un des quatre points échoue, ne pas l'activer, rien d'autre
   n'en dépend. Sous Docker Desktop le WAF peut voir l'adresse de la passerelle et non celle du PC Attaquant : aucun ban ne
   serait posé (sans danger, mais non démontré). Seuils par défaut à valider sur le trafic réel : 50 requêtes en 10 s, 3 adresses
   au plus, 5 minutes.
2. **Pré-créer la série `quotes/200` au démarrage de `payment`** (une ligne). Sans elle le détecteur est aveugle tant qu'aucun
   devis n'a été émis, et la procédure de reset de `docs/09` redémarre justement `payment`. Recommandé avant le live.
3. **Seuil de similarité du RAG** : une question hors sujet retrouve quand même 3 passages (~0,10), donc l'abstention repose sur le
   prompt d'un modèle de 1,5 Md. Le monter vers 0,12 écarterait ce cas mais pas tous les hors-sujet.
4. **Décision 3 (jeton HMAC)** : justification rédigée par moi à partir du code et de son commentaire, à valider ou corriger
   par l'équipe.
5. **Publier `/anomaly` à l'edge** : toujours non décidé (voir le rapport de mardi).
6. **Dette assumée** : la liste de `ETAT-SEMAINE.md` est mon inventaire ; l'équipe doit confirmer qu'elle est prête à défendre
   chaque ligne.

## Incidents

Aucun incident de sécurité : aucun secret suivi, aucun artefact dans le dépôt (vérifié, deux `__pycache__` de mes essais
supprimés après contrôle de leur contenu).

Transparence sur ce que j'ai exécuté, au-delà de la lecture seule :
- applications FastAPI en mémoire (`TestClient`, secrets factices en dossier temporaire) et la suite de tests ;
- **de vrais serveurs `uvicorn` sur loopback** (SQLite, dossiers temporaires) via le test natif du dépôt, deux fois : une fois
  tel quel (échec Ansible), une fois avec le bouchon ;
- la **commande Ansible exacte du remédiateur**, pour établir la cause de l'échec (elle échoue avant de lire le playbook) ;
- `npm ci` et `vite build` dans une copie jetable du front, hors du dépôt (le `node_modules` du dépôt n'a pas `vite`) ;
- venv jetable hors du dépôt : dépendances du projet aux versions épinglées, `pytest` et `pyyaml` non épinglés,
  `ansible-core` (inutilisable sous Windows), `langchain-*`, `uvicorn`, `jsonschema`.
Aucune commande Docker n'a été lancée. Deux fichiers de test temporaires créés puis supprimés.

## Reste à faire par un humain

Dans cet ordre, depuis WSL à la racine du dépôt :
1. Décider la pré-création de la série `quotes/200` (décision 2), sinon émettre un devis avant tout contrôle.
2. `docker compose up -d --build` (le `--build` est nécessaire : l'image embarque le code modifié), puis
   `python scripts/check_lundi.py`.
3. **Tester Ansible dans le conteneur, à froid** : `docker compose exec remediator python -m ansible.cli.playbook -i localhost,
   infra/ansible/contain.yml --syntax-check`. C'est le risque n°1.
4. Baseline puis modèle, puis calibration si besoin (`docs/05-ML-RAG.md`).
5. Attaque depuis le PC Attaquant pendant `python scripts/acceptance.py`, puis `python scripts/check_mercredi.py`
   (`--max-seconds 45` jeudi). Entre deux essais, réinitialiser le confinement (`docs/09`).
6. Optionnel : la surcouche de ban, avec sa checklist.
7. Sous Linux : `python -m pytest -q` en entier (avec le vrai Ansible et le registre sur PostgreSQL).
8. Hors dépôt : dossier PDF, support, clip (3 prises), archive (`scripts/package.py`), EBIOS ; relecture de `06`, `07`, `08`
   par P6 ; mise à jour du Kanban.
