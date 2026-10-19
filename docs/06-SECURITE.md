# Sécurité du prototype

## Périmètre et accès
Réseau du groupe : point d'accès mobile Windows RESILIENCE-G<n>, habituellement
192.168.137.0/24, Hôte 192.168.137.1. Vérifier l'adresse réelle. Le PC Attaquant
n'est connecté qu'à ce PA. Ne pas substituer une IP campus dans les scripts.
La cible du client offensif est bornée : `--target` (ou `LAB_TARGET`) n'accepte qu'une
IP littérale de 192.168.137.0/24 ou de loopback, tout autre hôte est refusé avant
connexion ; les redirections ne sont pas suivies (`docs/04-ATTAQUE.md`).
Aucun scan réseau, vol de données, persistance ou élévation de privilèges.

Le WAF est le seul point d'entrée applicatif. Routes autorisées dans Nginx ;
base, métriques, logs et contrôle sans publication réseau. Grafana localhost.
Sur Windows, créer une règle entrante TCP 8080 pour l'interface/adresse locale du
PA et le sous-réseau du groupe ; vérifier qu'aucune règle Docker plus large ne
rend le même port accessible via l'IP campus. Les interfaces diffèrent selon le
poste : inspecter Windows Defender Firewall et tester depuis le PC Attaquant.
Ne pas désactiver globalement le pare-feu pour faire fonctionner le prototype.

Les services Python (auth, payment, remediator, detector, rag) sont non-root, avec
root filesystem en lecture seule, capabilities retirées et no-new-privileges. Tous les
conteneurs ont une limite de RAM. Les journaux Docker ne sont bornés (2×5 Mo) que pour
auth, payment, remediator et detector. Le frontal est un nginx non privilégié, sans les
autres réglages. Les images tierces (WAF, base, observabilité, Ollama) peuvent nécessiter
un filesystem inscriptible ou des droits différents ; Alloy s'exécute en root pour lire
les journaux, en lecture seule. Elles ne sont pas décrites comme durcies intégralement.
Pas de montage docker.sock.

## Secrets
SOPS est le choix retenu parmi Vault/SOPS autorisés. age chiffre la clé de données.
`.secrets/secrets.enc.json` est chiffré ; `.secrets/age.key` est la clé privée et
ne doit jamais être transmise. `.secrets/runtime/*` contient les fichiers
nécessaires aux secrets Compose pendant l'exécution. Compose ne chiffre pas
ces fichiers sur disque : le chiffrement au repos provient de SOPS et des droits
sur le dossier. Parent 0700 ; fichiers montés lisibles par les services non-root.
Les valeurs ne sont ni dans le code, ni dans les arguments de commande, ni dans
le navigateur persistant. Garder la clé de déchiffrement et une copie chiffrée
hors du PC avant de supprimer les fichiers runtime. Le ZIP les exclut toutes.
Rotation : arrêter les services, générer de nouvelles valeurs par procédure dédiée,
réappliquer et tester ; changer le mot de passe PostgreSQL exige aussi un ALTER ROLE,
modifier seulement le fichier secret ne change pas une base déjà initialisée.

## Journaux
JSON métier : heure, composant, événement et identifiants fictifs. Pas de corps de
login, de token, de clé, de mot de passe ni de requête SQL contenant un secret.
WAF audit AFZ : métadonnées et headers de réponse, pas les corps/headers de requête.
Alloy expédie réellement ces fichiers vers Loki. Vérifier en recette qu'aucun
composant tiers n'ajoute des informations sensibles. Les logs métier JSON sur
volume ne tournent pas automatiquement dans cette version ; les archiver/purger
entre essais maîtrisés. Loki conserve 48h ; les fichiers de journaux Docker de auth,
payment, remediator et detector sont limités à 2×5Mo.
La machine Hôte peut altérer ses logs : aucune preuve d'inaltérabilité industrielle.

## Test WAF séparé de la reprise principale
Depuis le PC Attaquant, sur la seule URL du groupe :
`curl -i 'http://192.168.137.1:8080/api/ready?probe=%3Cscript%3Ealert(1)%3C%2Fscript%3E'`
C'est un marqueur XSS de test dans une query non exécutée par l'application.
Attendu : rejet CRS (souvent 403) et audit Loki `service="waf"` ; vérifier le résultat,
ne pas déclarer le WAF validé si la requête passe. Ne pas désactiver le WAF pour
faire passer le scénario. Les devis valides peuvent passer CRS tout en saturant
le métier : d'où une admission contextuelle en plus du filtrage de contenu.

## Budget de connexion et chemin de la reprise
Le service d'authentification limite les connexions à 30 par minute et par adresse
source qu'il voit (`services/auth/main.py`). Derrière le WAF et l'edge, tous les clients
publics lui arrivent avec l'adresse de l'edge : l'edge ne pose aucun `X-Forwarded-For` et
uvicorn n'en approuve aucun hors `127.0.0.1`. Le budget public est donc **partagé par tous
les clients**.

Risque constaté dans le code : le remédiateur se connectait par le WAF pour vérifier la
reprise, dans ce même budget. Un flot de connexions publiques pendant l'attaque pouvait
l'épuiser, la vérification recevait un 429 et l'incident passait en `failed` avec
`manual_review_required` : l'attaque provoquait ainsi, sans geste humain, le cas qui vaut
0/5 sur la remédiation.

Choix : le remédiateur obtient son jeton **directement auprès du service d'authentification,
par le réseau interne `app`** (variable `AUTH_URL`, `http://auth:8000` par défaut). Ce réseau
est déjà partagé par les deux services et n'est pas publié. L'adresse source vue par `auth`
est alors celle du conteneur remédiateur, donc un budget distinct par construction. La
limite publique est conservée : elle protège toujours contre l'essai de mots de passe. La
preuve métier (paiement puis lecture du registre) continue de passer par le WAF.

Garde-fou : `tests/test_login_budget.py` épuise le budget public (même le bon mot de passe est
alors refusé en 429) et vérifie que `business_verify` aboutit quand même. Un second test
rejoue l'ancien couplage et constate l'échec 429, pour prouver que le montage détecte la
panne ; un troisième interdit à `service_token` de nommer la route publique.

Compromis et risques résiduels :
- La vérification ne teste plus la connexion à travers le WAF, seulement le paiement.
- Un attaquant peut toujours verrouiller la **connexion publique** des opérateurs (le
  tableau de bord) en saturant ce budget partagé. C'est le coût d'une limite par adresse
  derrière un proxy ; l'amélioration industrielle est une limite par client réel avec une
  adresse d'origine posée par un proxy de confiance. Se connecter au tableau de bord avant
  la démonstration.
- Le remédiateur se connecte avec le compte opérateur `alice` et détient déjà `session_key` ;
  une identité de service dédiée au rôle minimal serait plus propre. Non faite : elle touche
  l'authentification, la vérification des jetons et le registre.

## Écarts avant tout usage industriel
TLS, OIDC/asymétrie des clés, moindre privilège DB (le rôle de création initial
a des droits larges dans ce prototype), séparation des capacités métier,
protection/rotation des logs, scan images et dépendances, digests immuables,
HA physique, supervision de l'IA, sauvegardes hors machine et restauration testée.
Le tag WAF `nginx` est mobile : relever puis figer son digest après le premier
pull réussi ; aucun digest non vérifié n'est inventé dans cette livraison.
