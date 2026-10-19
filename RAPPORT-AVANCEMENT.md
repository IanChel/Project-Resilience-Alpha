# Rapport d'avancement — 2026-10-19 (lundi)

## Verdict en une ligne
Le dépôt contient une implémentation technique **déjà très au-delà du jalon de
lundi** — chaîne attaque → détection ML → alerte signée → Ansible → vérification
métier complète et testée en natif — mais **rien n'est encore prouvé machine
allumée** (modèle non entraîné, secrets non générés, stack jamais démontrée) et
la remédiation **diverge de la checklist W1** (admission control applicatif, ni
recréation de conteneur ni ban d'IP).

## Alertes (par gravité, à traiter aujourd'hui)

1. **Tout repose sur du RUNTIME non prouvé.** Le détecteur est bloqué sur
   `waiting_for_trained_model` tant qu'aucun `model.joblib` n'existe
   ([services/detector/main.py:33-34](services/detector/main.py#L33-L34)) ; les
   secrets `.secrets/` ne sont pas générés ([scripts/init_secrets.py](scripts/init_secrets.py)) ;
   aucune trace d'un `docker compose up` réussi ni d'un run `acceptance.py`. Le
   **jalon critique M7** (pic Grafana + `anomaly=true`) est inatteignable sans
   d'abord : générer les secrets → démarrer la stack → collecter la baseline →
   entraîner le modèle. **C'est le chemin à dérisquer en premier.**

2. **La remédiation ne fait pas ce que la carte W1 décrit.** La chaîne est bien
   autonome (c'est acquis, pas de `0/5` en vue de ce côté), mais le playbook
   active une **politique d'admission applicative** ([infra/ansible/contain.yml:7-17](infra/ansible/contain.yml#L7-L17)),
   **sans recréer de conteneur ni bannir d'IP** — 2 des 8 items de la checklist
   W1. C'est défendable (moindre privilège, pas de socket Docker) et même aligné
   avec le sujet (« un conteneur qui redémarre ne suffit pas »), mais le pitch et
   le Trello doivent être **réalignés sur ce récit**, sinon le jury verra un écart
   entre ce qui est annoncé et ce qui tourne.

3. **Hygiène des secrets + bruit dans le dépôt.** Le scan ne trouve **aucun
   secret en clair** (bon), mais le `.gitignore` actif à la racine **ne couvre
   pas `.secrets/`** : dès que `init_secrets.py` tourne, `.secrets/runtime/*`
   (mots de passe en clair) risque d'être commité/zippé. En plus, des fichiers
   d'un ancien scaffold (`docker-compose.yml`, `ansible/remediate_dos.yml`,
   `services/orchestrator/`, `docs/API-CONTRACTS.md`) **coexistent et
   contredisent** l'implémentation réelle (`compose.yaml`, `infra/ansible/`,
   `services/remediator/`). À purger pour éviter qu'un correctif parte sur la
   mauvaise copie.

> Note méthodo : les deux commits sont des imports en masse du 19/10
> (`git shortlog` = 2 auteurs, 1 commit chacun). L'attribution P1→P6 par l'historique
> git est donc impossible ; la colonne « rôle » ci-dessous se base sur la
> complétude des dossiers de service, pas sur qui a commité.

## Avancement par jour

### LUNDI — 4 FAIT / 2 PARTIEL / 1 RUNTIME
| ID | Carte | Statut | Preuve | Ce qui manque |
|---|---|---|---|---|
| L1 | Squelette API FastAPI | FAIT | [services/payment/main.py:46-73](services/payment/main.py#L46-L73), modèle réel [services/payment/db.py:41-55](services/payment/db.py#L41-L55) | Endpoint nommé `/payments` (pas `/pay`) — sans impact |
| L2 | React + Tailwind | FAIT | [frontend/src/main.jsx:14-24](frontend/src/main.jsx#L14-L24), [frontend/package.json:16](frontend/package.json#L16) (tailwind 3.4.17) | — |
| L3 | docker-compose 5 services | FAIT | [compose.yaml](compose.yaml) : db, payment, prometheus, grafana, loki (+waf, alloy, rag…) | — |
| L4 | PC Attaquant + scénario DoS | PARTIEL | [scripts/attack_lab.py:14-15](scripts/attack_lab.py#L14-L15) (hôte 192.168.137.1 figé) | Le poste lui-même = `HORS-REPO` |
| L5 | Baseline + modèle ML | PARTIEL | Modèle **OneClassSVM** [services/detector/model.py:5-13](services/detector/model.py#L5-L13), collecte [services/detector/train.py](services/detector/train.py) | Baseline + `model.joblib` = artefacts runtime absents. ⚠️ pas IsolationForest |
| L6 | 4 contrats API + EBIOS + Kanban | FAIT | 4 specs [docs/openapi/](docs/openapi/) (auth/payment/rag/remediator) + [docs/03-INTERFACES.md](docs/03-INTERFACES.md) | EBIOS/Kanban = `HORS-REPO` |
| L7 | Sync point lundi | RUNTIME | Code L1+L3+L6 présent | À prouver stack démarrée + métriques dans Grafana |

### MARDI — 3 FAIT / 2 PARTIEL / 1 HORS-REPO / 1 RUNTIME
| ID | Carte | Statut | Preuve | Ce qui manque |
|---|---|---|---|---|
| M1 | API complète + JWT | FAIT | Persistance [db.py:41-55](services/payment/db.py#L41-L55) ; auth exigée [services/payment/main.py:60](services/payment/main.py#L60) | ⚠️ Jeton **HMAC signé maison**, pas un JWT standard ([services/common/security.py:22-45](services/common/security.py#L22-L45)) — à savoir défendre |
| M2 | Front paiement fonctionnel | FAIT | Appel réel + erreurs [frontend/src/main.jsx:12](frontend/src/main.jsx#L12) | — |
| M3 | Ansible base + /metrics | FAIT | [services/payment/main.py:53-55](services/payment/main.py#L53-L55) (prometheus_client), playbooks [infra/ansible/](infra/ansible/) | — |
| M4 | Script attaque DoS reproductible | FAIT | [scripts/attack_lab.py](scripts/attack_lab.py) (`--seconds`, borné 700 req/20 rps) | — |
| M5 | Modèle + /anomaly + seuil | PARTIEL | `fit` [detector/model.py:13](services/detector/model.py#L13), seuil `consecutive>=3 & score<0` [detector/main.py:41-43](services/detector/main.py#L41-L43) | **Pas d'endpoint `/anomaly`** : état via `/health` + boucle interne. Modèle non entraîné (runtime) |
| M6 | NIS2/DORA + PCA/PRA | HORS-REPO | Présents : [docs/06-SECURITE.md](docs/06-SECURITE.md), [docs/07-GOUVERNANCE.md](docs/07-GOUVERNANCE.md), [docs/08-PCA-PRA.md](docs/08-PCA-PRA.md) | Contenu non audité (gouvernance) |
| M7 | **Sync critique** (pic + anomaly=true) | RUNTIME | M4 et M5 existent → pas `ABSENT` | Modèle entraîné + stack + attaque réelle |

### MERCREDI — 1 FAIT / 4 PARTIEL / 2 RUNTIME
| ID | Carte | Statut | Preuve | Ce qui manque |
|---|---|---|---|---|
| W1 | **Moteur de remédiation** | PARTIEL | Chaîne complète (section dédiée ci-dessous) | 2/8 items : WAF rate-limit/ban IP + recréation conteneur |
| W2 | Dashboard SOC timeline | PARTIEL | Timeline incidents + polling 2 s [frontend/src/main.jsx:11,20](frontend/src/main.jsx#L11) | **Pas de chrono/compteur affiché** (exigé par la carte) |
| W3 | Transaction témoin auto | FAIT | [services/remediator/main.py:30-46](services/remediator/main.py#L30-L46) appelée en [:59](services/remediator/main.py#L59), vérifie `total_cents==200000` | — |
| W4 | WAF + SIEM + SOPS | PARTIEL | WAF ModSecurity `On` [compose.yaml:72-82](compose.yaml#L72-L82) ; SOC LogQL [services/detector/soc.py:4-19](services/detector/soc.py#L4-L19) ; SOPS+age [init_secrets.py:15-19](scripts/init_secrets.py#L15-L19) | **Ban d'IP automatique absent** ; le rate-limit est applicatif, pas WAF |
| W5 | RAG opérationnel | PARTIEL | LangChain+Ollama [services/rag/main.py:15-20](services/rag/main.py#L15-L20), sources retournées, ingestion [services/rag/retrieval.py](services/rag/retrieval.py) | Récupération **TF-IDF** (pas Chroma) ; génération runtime (503 si modèle non tiré, `generation_verified:False`) |
| W6 | Tests restauration chronométrés | RUNTIME | Harness + preuve JSON [scripts/acceptance.py:34-37](scripts/acceptance.py#L34-L37) | Temps réels = runtime |
| W7 | Sync mercredi <60 s | RUNTIME | — | Chrono bout-en-bout |

### JEUDI — 1 FAIT / 2 PARTIEL / 1 ABSENT / 3 HORS-REPO / 2 JALON
| ID | Carte | Statut | Preuve | Ce qui manque |
|---|---|---|---|---|
| J1 | Chaos 10× <45 s | PARTIEL | [scripts/acceptance.py](scripts/acceptance.py) (1 passe + évidence horodatée) | Pas de boucle ×10 ; chrono = runtime |
| J2 | Fiabiliser healthcheck + témoin | FAIT | Retries/backoff [remediator/main.py:36-46](services/remediator/main.py#L36-L46), test e2e [tests/test_native_chain.py](tests/test_native_chain.py) | Validation ×10 = runtime |
| J3 | run-demo.sh | ABSENT | — | Le fichier n'existe pas |
| J4 | Repo propre + doc ML/RAG | PARTIEL | Scan secrets **propre** (0 secret en clair) ; [docs/05-ML-RAG.md](docs/05-ML-RAG.md) | `.gitignore` ne couvre pas `.secrets/` ⚠️ ; fichiers scaffold en double à purger |
| J5 | Dossier PDF + pptx | HORS-REPO | Absents du dépôt | — |
| J6 | Clip Chrono | HORS-REPO | — | — |
| J7 | Répétition du live | HORS-REPO | — | — |
| J8 | Gel du code 17h00 | — | 2 commits, tous deux lundi 19/10 (09:51, 12:02) | Aucune violation (on est lundi) |
| J9 | Sync final | RUNTIME | — | Agrège J1-J4 |

### VENDREDI — HORS-REPO (soutenance)
| ID | Carte | Statut | Note |
|---|---|---|---|
| V1 | Démo live + pitch | HORS-REPO | — |
| V2 | Aucune intervention manuelle (0/5 sinon) | **Vérif code : OK** | Chemin nominal 100 % autonome (aucun `input()`/`confirm`). Branche d'échec → `manual_review_required=True` ([remediator/main.py:62](services/remediator/main.py#L62)) = garde-fou, pas une étape manuelle du nominal |
| V3 | 3 clips de secours | HORS-REPO | — |

## Moteur de remédiation — audit détaillé (checklist W1, le point 5/5)

| # | Item checklist | Statut | Preuve / commentaire |
|---|---|---|---|
| 1 | Détection ML branchée sur l'orchestrateur | **FAIT** | [detector/main.py:43-50](services/detector/main.py#L43-L50) poste une alerte **signée HMAC** ; [remediator/main.py:78-88](services/remediator/main.py#L78-L88) valide signature + fraîcheur + évidence |
| 2 | Orchestrateur déclenche le playbook Ansible | **FAIT** | [remediator/main.py:51-57](services/remediator/main.py#L51-L57) : `ansible.cli.playbook contain.yml`, timeout 25 s |
| 3 | Playbook active le WAF (rate-limit + ban IP) | **DIVERGENT** | [contain.yml:7-17](infra/ansible/contain.yml#L7-L17) active une **admission applicative** (`/control/contain`), **pas** le WAF ; **aucun ban d'IP**. Le WAF ModSecurity ne fait que du filtrage générique |
| 4 | Playbook recrée le conteneur compromis | **ABSENT** | Aucune recréation de conteneur. Choix délibéré : pas de socket Docker confié au remédiateur (durcissement, cf. [compose.yaml:46-52](compose.yaml#L46-L52)) |
| 5 | Healthcheck valide le retour à la normale | **FAIT** | [contain.yml:18-26](infra/ansible/contain.yml#L18-L26) (`/ready`, 10 retries) + vérif e2e |
| 6 | Transaction témoin rejouée automatiquement | **FAIT** | [remediator/main.py:36-44](services/remediator/main.py#L36-L44) : rejoue un paiement **via le WAF** + contrôle d'intégrité du registre (`total==200000`). Solide |
| 7 | Boucle complète sans intervention humaine | **FAIT** (nominal) | Aucun point d'entrée humain sur le chemin nominal ; reprise idempotente même après redémarrage [remediator/main.py:64-69](services/remediator/main.py#L64-L69) |
| 8 | Chrono <60 s (merc.) / <45 s (jeu.) | **RUNTIME** | Mesurable via `acceptance.py` ; jamais exécuté à ce stade |

**Lecture d'ensemble :** la chaîne est **réellement autonome et sa preuve
métier est meilleure que la moyenne** (rejeu de transaction + intégrité du
registre, pas un simple restart). Le risque n'est **pas** l'autonomie, c'est
l'**écart de récit** : la remédiation choisie est un *contrôle d'admission*, pas
une *recréation de conteneur + ban d'IP*. Deux options, à trancher en équipe :
(a) **assumer et réécrire** le pitch/Trello/W1 autour de l'admission control
(recommandé — cohérent avec le durcissement et avec le sujet), ou (b) ajouter la
recréation de conteneur, au prix d'un accès Docker qui affaiblit le durcissement.

## À vérifier machine allumée (cartes RUNTIME)

| Carte | Commande / manip exacte pour trancher |
|---|---|
| L5 / M5 / M7 | `python scripts/init_secrets.py` → `docker compose up -d` → générer du trafic normal → `python -m services.detector.train` → vérifier `model.joblib` créé et `/ops/ml` qui sort de `waiting_for_trained_model` |
| L7 | `docker compose up -d` puis ouvrir Grafana (127.0.0.1:3000) et voir les séries `lab_*` |
| W1 / W6 / W7 / J1 / J9 | Depuis le PC Hôte : `python scripts/acceptance.py --seconds 55` ; depuis le PC Attaquant : `python scripts/attack_lab.py --lab-authorized` → lire `PASS` + le JSON `runtime/evidence/` et le temps `created→recovered` |
| M7 (anomaly) | Pendant l'attaque : `GET /ops/ml` doit montrer `status=monitoring` et `score<0` ; au repos, `score>=0` |
| W5 | `docker compose exec ollama ollama pull qwen2.5:1.5b` puis poser une question via `/rag/ask` → réponse sourcée (sinon 503) |

## Hors dépôt (non noté)
EBIOS RM, Kanban (L6) · NIS2/DORA, PCA/PRA (M6, docs présents mais non audités) ·
Dossier PDF + pptx (J5) · Clip Chrono + 3 prises (J6, V3) · Répétition live (J7) ·
Mise en place physique du PC Attaquant (L4) · Démo live (V1).

## Répartition par rôle
| Rôle | FAIT | PARTIEL | ABSENT | Commentaire |
|---|---|---|---|---|
| P1 Back | L1, M1, M3, W3, J2 | — | — | **En avance.** API, persistance, auth, témoin, robustesse : le socle le plus abouti |
| P2 Front | L2, M2 | W2 | J3 | Écrans OK ; manque le **chrono** du dashboard et **run-demo.sh** |
| P3 Ops | L3, M3 | W1(⅓), W6 | — | Compose durci excellent ; dépend du runtime pour prouver W1/W7 |
| P4 Cyber | M4 | L4, W1(⅓), W4 | — | Attaque OK, WAF+SOC+SOPS en place ; **ban d'IP** et alignement W1 à traiter |
| P5 ML/Data | — | L5, M5, W5, J4 | — | Code ML/RAG présent mais **tout en attente de runtime** (modèle, Ollama) ; + nettoyage `.gitignore` |
| P6 PM/Gov | L6 | M6, W6 | — | Contrats figés ; gouvernance en `.md` non auditée ; livrables PDF/pptx/clip à venir |

---

**Prochaine action P1→P6 :** P5 lance `init_secrets.py` + `docker compose up` + entraîne le modèle (débloque M5/M7) ; P4 tranche l'alignement W1 (admission control assumé **ou** +ban IP) ; P2 ajoute le chrono dashboard + `run-demo.sh` ; P3 exécute `acceptance.py` pour produire la 1ʳᵉ preuve chronométrée ; P1 en appui robustesse ; P6 corrige le `.gitignore` (`.secrets/`) et purge les fichiers scaffold en double.
**Risque principal :** zéro preuve runtime à ce jour — tant que modèle + stack + un `acceptance.py PASS` ne sont pas obtenus, le jalon critique M7 et toute la chaîne restent théoriques.
**Temps avant gel du code :** jeudi 17h00 (on est lundi — environ 3,5 jours ouvrés).
