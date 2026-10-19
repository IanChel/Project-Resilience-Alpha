# Audit d'avancement — Project Resilience Alpha

Prompt à donner à l'agent VS Code. Place ce fichier et `trello-snapshot.json`
à la racine du dépôt, puis demande à l'agent :

> Lis `AUDIT-AVANCEMENT.md` et exécute la procédure.

---

## 1. Rôle

Tu es un auditeur technique. Tu compares **l'état réel du dépôt** au **plan de la
semaine** figé dans `trello-snapshot.json` (export du tableau Trello du groupe).

Tu produis un rapport d'avancement carte par carte. Tu ne corriges rien, tu
n'implémentes rien, tu ne modifies aucun fichier sauf le rapport de sortie.

## 2. Règles non négociables

1. **La preuve est dans le code, pas dans la doc.** Un README qui annonce une
   fonctionnalité ne vaut rien. Un fichier vide ou un `TODO` ne vaut rien. Une
   fonction qui `pass` ne vaut rien. Cherche l'implémentation réelle.
2. **Tu ne lances pas l'attaque DoS**, tu ne démarres pas la stack, tu
   n'exécutes aucun script du dépôt. L'audit est statique. Les seules commandes
   autorisées sont la lecture, la recherche (`grep`, `find`, `cat`) et `git log`
   / `git status` / `git diff --stat`.
3. **Distingue trois choses** : ce qui existe dans le code, ce qui est *censé*
   marcher, et ce qui ne peut être prouvé qu'en exécutant. Ne confonds jamais
   les deux dernières.
4. **Cite tes sources.** Chaque verdict renvoie à un chemin de fichier et, si
   possible, un numéro de ligne. Un verdict sans source est un verdict invalide.
5. **Pas de complaisance.** Ce plan est noté. Un « ça a l'air fait » qui se
   révèle faux jeudi soir coûte des points. En cas de doute, tu descends d'un
   cran et tu expliques le doute.

## 3. Barème

| Statut | Quand l'utiliser |
|---|---|
| `FAIT` | Le code existe, est complet et correspond au « Fait quand » de la carte. |
| `PARTIEL` | Le squelette est là mais il manque une partie explicite de la carte. Tu dis précisément ce qui manque. |
| `ABSENT` | Rien de probant dans le dépôt. |
| `RUNTIME` | Le code semble présent mais le critère de la carte ne peut être prouvé que machine allumée (chrono, pic Grafana, 5 exécutions, etc.). Tu listes la commande ou la manip exacte qui permettrait de trancher. |
| `HORS-REPO` | Livrable qui ne vit pas dans le dépôt (PDF, pptx, clip vidéo, validation humaine, EBIOS). Tu le signales sans le noter. |

## 4. Procédure

### Étape 1 — Cartographier le dépôt

Avant de juger quoi que ce soit, établis la carte du terrain :

```bash
git log --oneline -30
git status --short
find . -type f -not -path './.git/*' -not -path '*/node_modules/*' \
  -not -path '*/.venv/*' -not -path '*/__pycache__/*' | head -200
```

Note les langages, l'arborescence, les services, et **qui a commité quoi**
(`git shortlog -sne`) : ça te dit quels rôles P1→P6 ont réellement produit.

### Étape 2 — Charger le plan

Lis `trello-snapshot.json`. Il contient 33 cartes réparties sur 5 listes
(LUNDI → VENDREDI). Chaque carte a un `id`, un `titre`, des `roles` (P1→P6),
une `description` au format *Objectif / Contenu / Fait quand*, et parfois des
`checklists`.

**Le critère à auditer est la ligne « Fait quand » de la description.** C'est
elle qui fait foi, pas le titre.

### Étape 3 — Chercher les preuves

Pour chaque carte, cherche les preuves listées au §5. Utilise `grep -rn` sur le
dépôt. Si tu ne trouves rien avec les termes suggérés, élargis : le groupe a pu
nommer les choses autrement. Ne conclus `ABSENT` qu'après avoir vraiment cherché.

### Étape 4 — Écrire le rapport

Écris `RAPPORT-AVANCEMENT.md` à la racine, au format du §6. N'écris aucun autre
fichier.

---

## 5. Preuves attendues par carte

> Les chemins sont indicatifs. Ce qui compte c'est la **fonction**, pas le nom.

### LUNDI

| ID | Carte | Preuves à chercher |
|---|---|---|
| L1 | Squelette API FastAPI | Une app FastAPI ; routes `/pay` et `/health` (`@app.get`, `@app.post`, `APIRouter`) ; un modèle `Transaction` (SQLAlchemy / SQLModel) ; une migration (Alembic `versions/`) ou un `create_all`. |
| L2 | Projet React + Tailwind | `package.json` avec `react` ; `tailwind.config.*` ; un composant écran Paiement (formulaire) et un composant Dashboard SOC. Vérifie qu'ils ne sont pas vides. |
| L3 | docker-compose | `docker-compose.yml` avec **5 services** : base, api, prometheus, grafana, loki. Vérifie les `volumes` et le fichier `prometheus.yml` référencé. |
| L4 | PC Attaquant | Documentation réseau (`RESILIENCE-G6`, `192.168.137.1`) et choix du scénario DoS. Probablement dans `docs/` ou un README cyber. `HORS-REPO` en grande partie. |
| L5 | Baseline + modèle ML | Un dataset de baseline (`.csv`, `.parquet`) ou un script de collecte ; une mention de `IsolationForest` (`sklearn.ensemble`). |
| L6 | Contrats d'API + EBIOS + Kanban | Un fichier de contrat (OpenAPI/Swagger, `schemas.py`, `.proto`, ou un `docs/api-contracts.md`). **4 contrats attendus.** EBIOS et Kanban sont `HORS-REPO`. |
| L7 | Sync point lundi | `RUNTIME` : dépend de L1+L3+L6. Donne le verdict agrégé des trois. |

### MARDI

| ID | Carte | Preuves à chercher |
|---|---|---|
| M1 | API complète + JWT | Persistance réelle (`session.add`, `commit`) et non plus un mock ; JWT (`python-jose`, `PyJWT`, `OAuth2PasswordBearer`, `create_access_token`) ; une dépendance de sécurité sur les routes protégées. |
| M2 | Front paiement fonctionnel | Un appel HTTP réel depuis le front (`fetch`, `axios`) vers `/pay`, pas vers un mock ; affichage du résultat et branche d'erreur. Cherche s'il reste un `mock` actif. |
| M3 | Ansible + /metrics | Dossier Ansible (`playbooks/`, `*.yml` avec `hosts:`/`tasks:`) ; endpoint `/metrics` (`prometheus_client`, `Instrumentator`) ; job correspondant dans `prometheus.yml`. |
| M4 | Script d'attaque DoS | Un script d'attaque (`attack`, `dos`, `flood`, `hey`, `locust`, `ab`) **paramétrable** (args CLI / config), signe de reproductibilité. |
| M5 | Modèle + /anomaly + seuil | Entraînement (`fit(`) ; modèle sérialisé (`.pkl`, `.joblib`) ; endpoint `/anomaly` ; une constante de seuil explicite (`THRESHOLD`, `contamination=`). |
| M6 | NIS2/DORA + PCA/PRA | `HORS-REPO` sauf si des `.md` existent dans `docs/`. |
| M7 | Sync point mardi (critique) | `RUNTIME`. Vérifie quand même que M4 et M5 existent tous les deux — sans eux le jalon est `ABSENT`, pas `RUNTIME`. |

### MERCREDI

| ID | Carte | Preuves à chercher |
|---|---|---|
| W1 | **Moteur de remédiation** | Le point le plus important. Cherche un orchestrateur qui (a) consomme la sortie du ML, (b) déclenche Ansible (`ansible-playbook`, `subprocess`, `ansible_runner`), (c) agit sur le WAF, (d) recrée le conteneur (`docker restart/up`, API Docker), (e) repasse un healthcheck. **Vérifie qu'aucune étape n'attend une entrée humaine** (`input()`, `confirm`, `--interactive`, un bouton front). Couvre les 8 items de la checklist un par un. |
| W2 | Dashboard SOC timeline | Composant timeline ; source temps réel (WebSocket, SSE, polling) ; un chrono/compteur. Pas de données en dur. |
| W3 | Transaction témoin | Appel automatique de `/pay` déclenché **après** la remédiation, dans le code de l'orchestrateur, pas à la main. |
| W4 | WAF + SIEM + SOPS | Rate-limit (`slowapi`, `limiter`, conf nginx/traefik) ; ban d'IP ; règles de corrélation Loki/LogQL ; `.sops.yaml` ou fichiers `*.enc.*`. |
| W5 | RAG | `langchain` / `ollama` ; un index vectoriel (`chroma`, `faiss`) ; un script d'ingestion de la doc. |
| W6 | Tests de restauration | Relevés de temps dans un fichier (`.md`, `.csv`). Souvent `HORS-REPO`. |
| W7 | Sync point mercredi | `RUNTIME` : chrono sous 60 s. Dis si la chaîne W1 est complète sur le papier. |

### JEUDI

| ID | Carte | Preuves à chercher |
|---|---|---|
| J1 | Chaos 10× sous 45 s | Un script de répétition / harness de test ; des logs ou un fichier de résultats chronométrés. `RUNTIME` pour le chrono. |
| J2 | Fiabiliser healthcheck | Gestion des timeouts, retries, backoff autour du healthcheck et de la transaction témoin. Des tests unitaires sur ces cas limites comptent double. |
| J3 | run-demo.sh | Le fichier `run-demo.sh` existe, est exécutable, et remet vraiment l'état à zéro (`down -v`, purge, re-seed). |
| J4 | Repo propre + doc | **Fais un vrai scan de secrets** (commande au-dessous du tableau). Vérifie aussi `.gitignore` et l'absence de `.env` commité. Signale chaque occurrence avec son chemin — ne recopie jamais la valeur trouvée. |
| J5 | Dossier PDF + pptx | `HORS-REPO`. Signale leur présence/absence si le dépôt les contient. |
| J6 | Clip Chrono | `HORS-REPO`. |
| J7 | Répétition du live | `HORS-REPO`. |
| J8 | Gel du code 17h00 | `git log` : y a-t-il des commits après jeudi 17h00 ? Si oui, liste-les, c'est une alerte. |
| J9 | Sync point final | `RUNTIME` : agrège J1 à J4. |

Commande de scan de secrets pour J4 :

```bash
grep -rniE 'api[_-]?key|secret|passwd|password|token|private key' . \
  --exclude-dir={.git,node_modules,.venv,__pycache__,dist,build}
git log --all --name-only --pretty=format: | sort -u | grep -E '\.env|\.pem|\.key|credentials'
```

### VENDREDI

V1, V2, V3 sont `HORS-REPO` (soutenance). Pour **V2**, fais quand même une
vérification de code : cherche dans toute la chaîne de remédiation la moindre
étape qui exigerait une action humaine. Si tu en trouves une, c'est le risque
le plus coûteux du projet (0/5) — remonte-le en tête du rapport.

---

## 6. Format du rapport

Écris `RAPPORT-AVANCEMENT.md` :

```markdown
# Rapport d'avancement — <date>

## Verdict en une ligne
<Où en est le groupe par rapport au jour courant, en une phrase.>

## Alertes
<Les 3 points qui coûteront des points s'ils ne sont pas traités aujourd'hui.
Ordre de gravité. Si la chaîne de remédiation n'est pas autonome, c'est le n°1.>

## Avancement par jour

### LUNDI — x/7
| ID | Carte | Statut | Preuve | Ce qui manque |
|---|---|---|---|---|
| L1 | Squelette API FastAPI | FAIT | `api/main.py:12-48` | — |
...

(idem MARDI, MERCREDI, JEUDI, VENDREDI)

## Moteur de remédiation — audit détaillé
<Les 8 items de la checklist W1, un par un, avec le fichier et la ligne.
C'est le point noté 5/5 : il mérite sa propre section.>

## À vérifier machine allumée
<Liste des cartes RUNTIME, avec pour chacune la commande ou la manip exacte
qui permettrait de trancher.>

## Hors dépôt
<Cartes HORS-REPO, pour mémoire, non notées.>

## Répartition par rôle
| Rôle | FAIT | PARTIEL | ABSENT | Commentaire |
|---|---|---|---|---|
<Qui est en avance, qui est en retard. Factuel, basé sur le code et git shortlog.>
```

## 7. Après le rapport

Termine ta réponse par **trois lignes maximum** :
la prochaine action concrète pour P1→P6, le risque principal, et le temps
restant avant le gel du code (jeudi 17h00).

Ne propose pas de corriger le code dans la foulée. L'audit et la correction sont
deux demandes séparées.
