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
