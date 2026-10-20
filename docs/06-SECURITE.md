# Sécurité du prototype

## Périmètre et accès
Réseau du groupe : point d'accès mobile Windows RESILIENCE-G2, habituellement
192.168.137.0/24, Hôte 192.168.137.1. Vérifier l'adresse réelle. Le PC Attaquant
n'est connecté qu'à ce PA. Ne pas substituer une IP campus dans les scripts.
La cible du client offensif est bornée : `--target` (ou `LAB_TARGET`) n'accepte qu'une
IP littérale de 192.168.137.0/24 ou de loopback, tout autre hôte est refusé avant
connexion ; les redirections ne sont pas suivies (`docs/04-ATTAQUE.md`).
Aucun scan réseau, vol de données, persistance ou élévation de privilèges.

Le WAF est le seul point d'entrée applicatif. Routes autorisées dans Nginx ;
base, métriques, logs et contrôle sans publication réseau. Grafana localhost.
Sur Windows, créer une règle entrante TCP sur le port publié (`LAB_PORT`, 8081) pour l'interface/adresse locale du
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
Conséquence mesurée du durcissement : la racine du remédiateur étant en lecture seule et Ansible
résolvant `~` via la base passwd (`/home/app`) plutôt que `$HOME`, ses répertoires temporaires sont
redirigés sous `/tmp` (`ANSIBLE_HOME`, `ANSIBLE_LOCAL_TEMP`, `ANSIBLE_REMOTE_TEMP` dans `compose.yaml`).
Sans cela, **tout module Ansible échoue** et chaque incident finirait en `manual_review_required` :
c'est le scénario à 0/5. `--syntax-check` ne détecte pas ce défaut, seule l'exécution d'un module le
révèle ; `tests/test_configs.py` fige la configuration.

## Secrets
SOPS (*Secrets OPerationS*) est un éditeur de fichiers de secrets chiffrés, choisi
dans le projet parmi Vault/SOPS autorisés. Il chiffre le fichier structuré
`.secrets/secrets.enc.json` avec le destinataire public age. La clé publique age
sert au chiffrement ; la clé privée age sert uniquement au déchiffrement. Il ne
faut jamais chiffrer avec la clé privée. age chiffre la clé de données.
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
`curl -i 'http://192.168.137.1:8081/api/ready?probe=%3Cscript%3Ealert(1)%3C%2Fscript%3E'`
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

## Limitation de débit : où elle se situe réellement
État constaté, rien n'est déplacé. **Aucune limitation de débit n'existe au niveau du WAF ni de l'edge** :
`infra/nginx/default.conf` n'a ni `limit_req` ni `limit_conn`, et ce dépôt ne configure pas la
protection DoS de CRS. Les limites sont **applicatives** :

| Où | Quoi | Fichier |
|---|---|---|
| Authentification | 30 connexions par minute et par adresse vue (celle du proxy, donc partagée) | `services/auth/main.py` |
| Paiement, capacité | 4 emplacements partagés entre devis et paiements, au-delà `503` : c'est de la capacité, pas une limite par client | `services/payment/main.py` |
| Paiement, confinement | après la remédiation, un devis par identité et par seconde (`429`) | `services/payment/main.py` |
| WAF | filtrage de contenu CRS ; la seule réaction par adresse est le ban temporaire de la décision 1, en surcouche optionnelle | `compose.ban.yaml` |

Conséquence à connaître : le WAF ne ralentit pas un flot de requêtes **valides** (un devis valide passe CRS) ;
c'est le contrôle d'admission applicatif qui le fait, une fois l'incident détecté.

## Décision 1 : bannissement temporaire de l'adresse de l'attaquant
**Ce qui est fait.** Après avoir contenu l'attaque, le playbook peut bannir au WAF les adresses
sources de l'alerte. L'adresse n'est **jamais** lue dans un en-tête de requête : un client qui
contrôle `X-Forwarded-For` ferait sinon bannir l'adresse de son choix, y compris celle du proxy, ce qui
couperait tout le service. Le détecteur la mesure à l'adresse du **pair vu par le WAF lui-même**
(son journal d'accès, expédié à Loki par Alloy), la met dans l'alerte **signée**, et le remédiateur
filtre : seules les adresses du sous-réseau du lab (`192.168.137.0/24`) sont bannissables, **jamais
l'hôte** (qui porte l'observateur), jamais une adresse interne Docker (la transaction témoin part du
conteneur remédiateur, hors de ce sous-réseau), au plus 3 adresses par alerte. Chaque ban expire
(5 minutes) ; un ban déjà actif garde son échéance, donc le rejeu ne change rien. Le ban est au mieux :
son échec ne fait jamais échouer le confinement. La preuve est relue dans le fichier (`ban.applied`
dans `/ops/status`), pas supposée. Code et tests : `services/remediator/bans.py`, `tests/test_ban.py`.

**Ce qui n'est pas vérifié.** Le dépôt prouve la **décision** (adresse, filtres, expiration,
idempotence, transaction témoin avec un ban actif), pas son **application** au WAF, que personne n'a
pu exécuter. Elle est donc une surcouche optionnelle, `compose.ban.yaml`, hors de la stack de base, qui
repose sur trois hypothèses sur l'image du WAF (journal d'accès via `ACCESSLOG`, chargement d'un fichier
de règles monté, rechargement par `SIGHUP` d'un conteneur à capacité `KILL` seule, sans socket Docker).
Deuxième incertitude : sous Docker Desktop, le WAF peut voir l'adresse de la passerelle Docker et non
celle du PC Attaquant ; elle est exclue (hors sous-réseau), donc **aucun ban n'est posé**, sans danger.

**Pour l'activer, et le valider en exécution.** `docker compose -f compose.yaml -f compose.ban.yaml up -d`,
puis : (1) `/var/log/modsecurity/access.log` existe dans le WAF et sa première colonne est l'adresse du
client ; (2) pendant l'attaque, Loki renvoie l'adresse du PC Attaquant pour `{service="wafaccess"}` ;
(3) après l'alerte, `/ops/status` montre `ban.applied` et le PC Attaquant reçoit un 403 du WAF alors que la
transaction témoin réussit ; (4) après 5 minutes `/bans/ban.list` est vide. Si l'un des quatre échoue,
ne pas l'activer pour la soutenance : rien d'autre n'en dépend. Risque assumé : un client légitime du
sous-réseau qui dépasserait 50 requêtes en 10 s pendant une alerte serait banni 5 minutes.

## Décision 2 : on ne recrée pas le conteneur (« pourquoi vous ne redémarrez pas le conteneur ? »)
**Ce qu'on fait à la place.** Notre moteur ne remplace aucun conteneur : il contient. Il applique dans
l'application un contrôle d'admission (un devis par identité et par seconde, persisté sur volume et
idempotent), éventuellement bannit l'adresse de l'attaquant au WAF, puis il **prouve** la reprise par une
vraie transaction et la conservation du registre, pas par l'état d'un conteneur. Le service n'est jamais
arrêté : le contrôle agit pendant que l'attaque continue.

**Pourquoi.** Recréer un conteneur exigerait de confier au moteur le socket Docker, c'est-à-dire un pouvoir
équivalent à root sur la machine hôte, à un service qui traite des entrées venues du réseau. Un moteur
compromis pourrait alors démarrer n'importe quel conteneur et monter le disque de l'hôte. Le sujet demande
justement de ne pas introduire « une interface d'administration accessible à n'importe quel composant ».
Nous lui donnons deux pouvoirs étroits : appeler une action fixe sur le service de paiement avec un secret
dédié, et écrire une liste de bannissement.

**Ce que ça coûte.** Ce choix traite une saturation qu'on peut contenir. Un conteneur **compromis** (code
altéré, mémoire corrompue) ne serait pas remplacé : on contient, on ne reconstruit pas. Pour ce cas la
réponse est une décision d'opérateur, hors du moteur : confinement, investigation, puis reconstruction
depuis une image saine (le PRA, `08-PCA-PRA.md`, rappelle qu'un simple retour du paiement ne résout pas
une compromission ; la procédure de reconstruction n'y est pas détaillée). Le `restart: unless-stopped`
de Docker, lui, n'est pas une remédiation.

## Décision 3 : jeton de session signé HMAC, pas un JWT
*Justification rédigée à partir du code et de son commentaire (« lab-only signed session tokens, no
external identity provider »), à valider par l'équipe.*

**Ce qu'on a fait.** Le service d'authentification émet `base64url(payload).base64url(HMAC-SHA256)`, avec
l'identité, le rôle, l'audience `resilience-lab` et une expiration à 1 h ; chaque service le vérifie avec la
même clé `session_key`, un secret Docker (`services/common/security.py`). Il n'y a que deux comptes fictifs et
aucun fournisseur d'identité : une quarantaine de lignes lisibles, testées (jeton falsifié ou expiré refusé,
`tests/test_api.py`), plutôt qu'une bibliothèque de jetons standard dont il faut maîtriser les options (algorithmes acceptés,
clés, rotation) en quatre jours. Le format n'est donc pas standard : le contrat le déclare comme jeton
`bearer` HMAC maison, jamais comme un jeton standard (`docs/openapi/*.json`).

**Ce que ça coûte.** La clé est symétrique et partagée : **tout service qui la détient peut émettre un jeton
opérateur**, pas seulement le vérifier. Le remédiateur et le RAG la détiennent (`07-GOUVERNANCE.md`, risque sur le
RAG). Pas de rotation ni de révocation avant l'expiration. Aucun outil tiers ne sait lire ce format. En contexte
industriel : OIDC avec clés asymétriques, où seul l'émetteur peut signer (voir ci-dessous).

## Écarts avant tout usage industriel
TLS, OIDC/asymétrie des clés, moindre privilège DB (le rôle de création initial
a des droits larges dans ce prototype), séparation des capacités métier,
protection/rotation des logs, scan images et dépendances, digests immuables,
HA physique, supervision de l'IA, sauvegardes hors machine et restauration testée.
Le tag WAF `nginx` est mobile : relever puis figer son digest après le premier
pull réussi ; aucun digest non vérifié n'est inventé dans cette livraison.
