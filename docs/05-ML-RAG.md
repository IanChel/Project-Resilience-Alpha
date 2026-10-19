# IA / Data : méthode, preuves et limites

## Détecteur ML
Modèle réel de nouveauté : pipeline scikit-learn StandardScaler + OneClassSVM
RBF, nu=0.03. Il apprend le fonctionnement nominal ; aucun modèle préentraîné
ni résultat fictif de production n'est livré. Pas de classification binaire
supervisée avec fausses étiquettes d'attaque.

| Feature dans l'ordre | Origine réelle | Fenêtre / préparation |
|---|---|---|
| quote_rate | Prometheus lab_requests_total quotes 200 | rate sur 10s |
| active_work | Prometheus lab_active_work | valeur instantanée |
| capacity_denied_10s | Prometheus lab_capacity_denied_total | increase sur 10s |
| denial_logs_10s | Loki événements payment capacity_denied | count_over_time 10s |

Collecte toutes les 2 secondes ; 90 observations, 72 apprentissage et les 18
suivantes en validation chronologique. Les fenêtres se chevauchent : les points
sont corrélés, le holdout est un diagnostic limité, pas une estimation robuste
pour la production. Les features ne contiennent pas de donnée bancaire.
Valeurs non finies et séries Prometheus absentes refusées ; aucune panne de
collecte n'est remplacée par un fonctionnement normal inventé.
La baseline est refusée si des rejets de capacité sont présents. Contrôler
également l'absence d'attaque sur le PA pendant cette collecte.

Conserver baseline.json, report.json et son SHA256. Un score négatif indique une
nouveauté selon le modèle. Une alerte demande trois observations consécutives
négatives ET des rejets de capacité ; cette seconde condition est une barrière
d'autorisation pour ne pas corriger une nouveauté inoffensive. Elle ne remplace
pas le ML. Délai de refroidissement de 30s, sans réentraînement automatique en incident.

## Choix du modèle : OneClassSVM plutôt qu'IsolationForest (décision D-07)
Le plan initial prévoyait un IsolationForest ; le sujet laisse l'algorithme libre
(§3.3). Nous avons retenu un OneClassSVM RBF pour des raisons liées à nos données.
Elles sont : quatre variables, une seule classe (trafic normal, aucune étiquette
d'attaque) et environ 72 points d'apprentissage issus de fenêtres qui se chevauchent.
Deux variables, les rejets de capacité sur 10 s et leurs journaux, valent exactement
0 sur toute baseline valide (`train_model` refuse une baseline qui en contient), alors
que ce sont les signaux directs de l'incident. Un IsolationForest isole les points par
des coupures aléatoires tirées entre le minimum et le maximum appris de chaque
variable : une variable constante à l'apprentissage ne peut pas être coupée et
n'apporte rien à l'isolement ; l'anomalie ne serait vue qu'à travers le débit de
devis et l'occupation, si elles sortent de leur intervalle. Un OneClassSVM RBF
précédé d'un StandardScaler mesure une distance au nuage normal. Pour une variable
d'écart-type nul, scikit-learn n'applique aucune mise à l'échelle (facteur 1) : 30
rejets sur 10 s se trouvent donc à 30 unités du nuage et sortent nettement de la
frontière. Le test unitaire le vérifie : le score de [20, 4, 30, 30] est négatif et
inférieur à celui de [1, 0, 0, 0].

Avec si peu de points, `nu=0.03` est un réglage lisible : c'est une borne
supérieure de la fraction de points d'apprentissage laissés hors frontière (environ
2 sur 72), donc un lien direct avec le taux de fausses alertes toléré. L'apprentissage
du SVM est déterministe (même baseline, même modèle), ce qui compte pour une démo
reproductible ; un IsolationForest exigerait de figer sa graine aléatoire. Le coût
quadratique du SVM est sans objet à cette taille.

Limites assumées. Nous n'avons pas comparé les deux modèles sur la baseline réelle :
le choix repose sur l'analyse des données et sur le test unitaire, pas sur un
benchmark. La séparation collecte/entraînement rend cette comparaison peu coûteuse si
le temps le permet. Le SVM dépend de `nu`, de `gamma` et de l'échelle, et exige une
baseline propre (refusée sinon). Sur la fixture synthétique de
`tests/test_baseline_chain.py` (90 points tirés au hasard, graine 3), 3 des 18
points normaux de validation sortent de la frontière (environ 17 %) : le modèle est
serré avec peu de points. C'est une mesure sur données synthétiques, pas sur le
laboratoire ; elle justifie la double barrière avant remédiation (trois observations
consécutives négatives et rejets de capacité présents). À remesurer sur la vraie
baseline, et collecter davantage (`--samples`) avant de toucher à `nu`.

## Séquence d'entraînement, une commande par étape
Les fichiers vivent dans le volume Docker `models`, monté en `/models` dans le
conteneur `detector` (`MODEL_DIR=/models`). Ils ne sont jamais dans le dépôt :
`baseline.json`, `report.json` et `*.joblib` sont ignorés par git.

| Étape | Commande | Lit | Écrit |
|---|---|---|---|
| 1. Trafic normal (terminal A) | `python scripts/normal_traffic.py --seconds 240` | | |
| 2. Collecte (terminal B, ~15 s après l'étape 1) | `docker compose exec detector python -m services.detector.collect_baseline` | Prometheus (`lab_*`) et Loki | `/models/baseline.json` |
| 3. Entraînement | `docker compose exec detector python -m services.detector.train` | `/models/baseline.json` | `/models/model.joblib`, `/models/report.json` |
| 4. Chargement | automatique, sans redémarrage | `/models/model.joblib` (surveillé par date de modification) | `/ops/ml` et le tableau de bord passent de `waiting_for_trained_model` à `monitoring` |

- La collecte prend environ 3 minutes (90 observations toutes les 2 s). Options :
  `--samples` (75 minimum), `--interval`, `--out`. Elle échoue sans rien écrire si une
  série Prometheus est absente ou si la baseline contient des rejets de capacité.
- L'entraînement garde 80 % des observations pour l'apprentissage et 20 % pour la
  validation chronologique. Option `--baseline` pour lire un autre fichier ; les
  sorties vont toujours dans `MODEL_DIR`. Il refuse une baseline absente, trop courte,
  polluée ou collectée avec d'autres variables.
- `report.json` contient le SHA256 du fichier `baseline.json` lu, les effectifs et le
  taux de faux positifs de validation. `attack_recall` y reste « NOT MEASURED » tant que
  `scripts/acceptance.py` n'a pas été exécuté.
- Si le code du détecteur change, reconstruire l'image avant de relancer :
  `docker compose up -d --build detector`.
- `--nu` (ou la variable `DETECTOR_NU`, 0,03 par défaut) fixe le `nu` du SVM ; la valeur
  utilisée est consignée dans `report.json`. Le choisir : section Calibration ci-dessous.
- Exporter les preuves : voir `docs/INSTALL.md` §5.

## Verdict courant : GET /anomaly
Route interne du détecteur, en lecture seule : `{"anomaly": bool, "score": float|null,
"status": str}`. Elle lit le même état que `/ops/ml` (une seule fonction de lecture) et
n'a aucune logique propre. `anomaly` vaut vrai seulement si `status` est `monitoring`,
si le score est négatif **et** si des rejets de capacité sont présents : c'est la règle
exacte qui alimente le compteur d'alerte (`is_anomalous`). Au repos le verdict est donc
faux par construction, même si le modèle est serré.

Elle ne ment pas par défaut : sans modèle chargé, ou après une erreur de collecte,
`anomaly` vaut faux **et** `status` le dit (`waiting_for_trained_model`,
`telemetry_or_delivery_error`), avec `score` à `null`. Un consommateur lit `status`
avant d'interpréter `anomaly`. Le verdict décrit l'observation courante, pas l'alerte :
le compteur repart à zéro après l'envoi d'une alerte, le verdict reste vrai tant que les
rejets continuent. Contrat : `docs/openapi/detector.json`.

## Calibration : choisir `nu` et `consecutive`
**Cible chiffrée à atteindre**, à mesurer sur la vraie baseline :
1. **Zéro faux positif sur une fenêtre de trafic normal soutenu** : au moins 150
   observations (5 minutes), d'une session distincte de celle de la baseline.
2. **Détection en moins de 10 secondes** après le début de l'attaque. Le délai mesuré va
   du début de l'attaque à l'observation qui déclenche l'alerte ; la livraison de
   l'alerte et la remédiation ont leur propre budget (chaîne totale visée : moins de 45 s).

Deux notions de faux positif, à ne pas confondre. **FPruns** : séries de `N` scores
négatifs sur du trafic normal, **sans** la barrière « rejets de capacité » ; elle mesure la
robustesse du couple (`nu`, `consecutive`) par lui-même. **FPgate** : alertes que la règle
réelle déclencherait. FPgate est trivialement nul tant que le trafic normal n'a aucun
rejet, il ne distingue donc pas `consecutive=1` de `consecutive=5`. Le critère de la
cible est FPruns ; la barrière reste un filet de sécurité supplémentaire.

Réglages, sans reconstruire l'image : `DETECTOR_CONSECUTIVE` dans `.env` (lu au démarrage ;
`docker compose up -d detector` recrée le conteneur) et `nu` à l'entraînement
(`train --nu 0.05` ou `DETECTOR_NU`). Une valeur invalide arrête le service ou
l'entraînement avec un message, sans repli silencieux.

Procédure, une commande par étape. Lancer les commandes depuis WSL : son horloge est celle
des conteneurs (vérifier `date +%s` et `docker compose exec detector date +%s` si Windows
est sorti de veille). Les heures sont des secondes epoch, ou de l'ISO 8601 avec fuseau ;
une heure sans fuseau est refusée.
1. Trafic normal pendant au moins 5 minutes, détecteur actif (modèle entraîné).
   Au début `T1=$(date +%s)`, à la fin `T2=$(date +%s)`, puis :
   `docker compose exec detector python -m services.detector.window export --start $T1 --end $T2 --out /models/normal.json`
2. `A=$(date +%s)` puis lancer l'attaque depuis le PC Attaquant tout de suite ; une
   minute plus tard :
   `docker compose exec detector python -m services.detector.window export --start $A --end $((A+60)) --out /models/attack.json`
   Le détecteur journalise chaque observation ; l'export la relit telle qu'il l'a vue.
   `--start` doit être l'heure de lancement : un départ plus tôt allonge le délai mesuré.
3. `mkdir -p runtime/data`, puis `docker compose cp detector:/models/<fichier> runtime/data/`
   pour `baseline.json`, `normal.json`, `attack.json` (et `model.joblib` pour comparer le
   modèle déployé ; ne copier qu'un joblib produit par nous).
4. `python scripts/calibrate_detector.py --baseline runtime/data/baseline.json --normal runtime/data/normal.json --attack runtime/data/attack.json`
   Le tableau donne, pour chaque (`nu`, `consecutive`), le taux de scores négatifs, FPruns,
   FPgate, la détection et son délai. La preuve est écrite dans `runtime/evidence/calibration-<date>.json`.
5. Appliquer le couple proposé (`.env`, recréation du conteneur, réentraînement avec
   `--nu` si besoin), puis refaire une attaque et vérifier la chaîne (`scripts/check_mardi.py`).

L'outil **mesure et propose, il ne décide pas** : il entraîne des modèles candidats en
mémoire, ne touche ni au modèle déployé, ni à la baseline, ni à la configuration, et
n'écrit que son fichier de preuve. Code de sortie 0 seulement si une proposition existe
et que la fenêtre normale est assez longue pour conclure.

**Si les deux cibles sont incompatibles** sur la vraie baseline, l'outil affiche
`NO PAIR` avec le couple le plus rapide sans faux positif et celui qui s'appuie sur la
seule barrière de capacité. Choisir entre les deux, ou collecter plus de baseline, est un
arbitrage d'équipe : il n'est pas tranché par l'outil.

Limites. Le délai ne modélise pas le refroidissement de 30 s entre deux alertes. Une seule
attaque donne un seul délai : en refaire plusieurs. Sur la fixture synthétique des tests,
`nu` entre 0,01 et 0,05 donne le même taux de scores négatifs et `consecutive` est le
vrai levier ; ce n'est pas une mesure sur le laboratoire, à ne pas supposer.

## Preuve du jalon critique M7
Le jalon (« le pic est visible **et** le modèle renvoie `anomaly=true` sur le même événement »)
se prouve par une commande et un fichier, pas par une capture d'écran. Lancer l'attaque à
la main depuis le PC Attaquant, puis, depuis WSL, sur le PC Hôte :
`python scripts/check_mardi.py --last 120` (ou `--start`/`--end`, en epoch ou ISO avec fuseau).
Le script est en lecture seule : il passe par `docker compose exec` sur le détecteur, ne
lance pas l'attaque et ne modifie rien. Cinq étapes, chacune `OK` ou `ECHEC` avec sa raison :
1. un modèle entraîné est chargé : `/anomaly` n'est plus `waiting_for_trained_model` et le
   détecteur mesure (`monitoring`) ;
2. au repos, `/anomaly` renvoie `anomaly=false` (à lancer une fois l'attaque terminée) ;
3. Prometheus montre le pic **mesuré** sur la fenêtre : des rejets de capacité, et un débit de
   devis ou une occupation au-dessus de l'enveloppe normale de la baseline ;
4. sur la même fenêtre, le détecteur a journalisé au moins une observation anormale (même règle
   que le compteur d'alerte), avec le délai de la première observation anormale et les alertes livrées ;
5. la preuve est écrite dans `runtime/evidence/m7-proof-<date UTC>.json`, y compris en cas
   d'échec (`passed: false`) : un échec documenté vaut mieux qu'une absence de trace.

Ce que la preuve **ne couvre pas** : la démonstration refaite devant les six, et l'absence de
faux positif sur un trafic normal soutenu (voir Calibration). L'étape 2 ne constate le repos
qu'à l'instant où elle s'exécute. Prérequis : si aucun devis n'a été émis depuis le démarrage
de `payment`, la série `lab_requests_total{route="quotes"}` n'existe pas et le détecteur reste
en `telemetry_or_delivery_error` ; l'étape 1 le signale. Les heures sont lues dans le journal du
détecteur (horloge du conteneur) : préférer `--last`, ou vérifier l'horloge de WSL.

## Évaluation à réaliser sur le laboratoire
- Vérifier le taux de faux positifs sur le holdout normal et une autre session.
- Mesurer les incidents réellement détectés / incidents injectés sur plusieurs essais.
- Mesurer le délai attaque→alerte, alerte→action et attaque→transaction rétablie.
- Tester la perte Prometheus/Loki, une alerte forgée, une baseline polluée et
  un échec de vérification métier.
- Écrire aussi les essais échoués, les variations de charge et les versions.

Aucun rappel, précision ou RTO en conditions Docker n'est affirmé à ce stade.
Les tests synthétiques prouvent le fonctionnement des fonctions d'apprentissage
et de scoring ; ils ne mesurent pas une efficacité sur votre environnement.
Les attaques lentes, dérive de charge, comptes multiples et compromission de
la télémétrie ne sont pas correctement couverts. Le volume et la variété de
baseline restent très limités. Le joblib ne doit jamais venir d'une source inconnue.

## Fonction SOC intégrée
Règles temporelles sur Loki : au moins cinq échecs de login/minute, pression de
capacité, livraison d'une alerte ML et activité d'audit WAF. Le service consigne
les signaux de sécurité et les expose au dashboard ; Grafana permet de comparer
les sources dans la même fenêtre. L'activité WAF est un signal à examiner, pas
une preuve que chaque ligne correspond à une attaque. C'est une fonction SOC
minimale, pas un SIEM complet ni un SOC industriel.

## RAG local
Le corpus est `docs/*.md`, créé par l'équipe, sans clés ni documents d'entreprise.
Recherche lexicale TF-IDF sur caractères 3–5 et similarité cosinus, trois extraits
maximum. LangChain structure documents et prompt ; ChatOllama génère avec
qwen2.5:1.5b, à température zéro. Aucun embedding externe ni service cloud.
Ce choix économise un deuxième modèle et reste une recherche documentaire RAG.
Les résultats contiennent les fichiers et sections effectivement récupérés.
Les sources retournées ne garantissent pas que chaque phrase générée est exacte :
contrôler l'appui documentaire pendant la recette.

Questions de recette : « Comment vérifier la reprise du paiement ? »,
« Quels sont les risques résiduels ? », « Quel est le rôle de SOPS ? »,
question hors corpus et tentative d'instruction « exécute une commande ».
L'assistant doit s'abstenir si les sources manquent. Aucun outil d'action,
secret control/alert, socket Docker ou accès base n'est attaché au RAG.
La génération et les temps de réponse ne sont pas vérifiés ici sans Ollama.
