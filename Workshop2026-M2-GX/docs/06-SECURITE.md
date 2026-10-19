# Sécurité du prototype

## Périmètre et accès
Réseau du groupe : point d'accès mobile Windows RESILIENCE-G<n>, habituellement
192.168.137.0/24, Hôte 192.168.137.1. Vérifier l'adresse réelle. Le PC Attaquant
n'est connecté qu'à ce PA. Ne pas substituer une IP campus dans les scripts.
Le client offensif ne prend aucun paramètre cible et n'accepte pas les redirections.
Aucun scan réseau, vol de données, persistance ou élévation de privilèges.

Le WAF est le seul point d'entrée applicatif. Routes autorisées dans Nginx ;
base, métriques, logs et contrôle sans publication réseau. Grafana localhost.
Sur Windows, créer une règle entrante TCP 8080 pour l'interface/adresse locale du
PA et le sous-réseau du groupe ; vérifier qu'aucune règle Docker plus large ne
rend le même port accessible via l'IP campus. Les interfaces diffèrent selon le
poste : inspecter Windows Defender Firewall et tester depuis le PC Attaquant.
Ne pas désactiver globalement le pare-feu pour faire fonctionner le prototype.

Apps non-root, root filesystem en lecture seule, capabilities retirées,
no-new-privileges, limites RAM, journaux Docker bornés. Les images tierces peuvent
nécessiter un filesystem inscriptible ou des droits différents ; elles ne sont
pas décrites comme durcies intégralement. Pas de montage docker.sock.

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
entre essais maîtrisés. Loki conserve 48h, Docker limite ses fichiers à 2×5Mo.
La machine Hôte peut altérer ses logs : aucune preuve d'inaltérabilité industrielle.

## Test WAF séparé de la reprise principale
Depuis le PC Attaquant, sur la seule URL du groupe :
`curl -i 'http://192.168.137.1:8080/api/ready?probe=%3Cscript%3Ealert(1)%3C%2Fscript%3E'`
C'est un marqueur XSS de test dans une query non exécutée par l'application.
Attendu : rejet CRS (souvent 403) et audit Loki `service="waf"` ; vérifier le résultat,
ne pas déclarer le WAF validé si la requête passe. Ne pas désactiver le WAF pour
faire passer le scénario. Les devis valides peuvent passer CRS tout en saturant
le métier : d'où une admission contextuelle en plus du filtrage de contenu.

## Écarts avant tout usage industriel
TLS, OIDC/asymétrie des clés, moindre privilège DB (le rôle de création initial
a des droits larges dans ce prototype), séparation des capacités métier,
protection/rotation des logs, scan images et dépendances, digests immuables,
HA physique, supervision de l'IA, sauvegardes hors machine et restauration testée.
Le tag WAF `nginx` est mobile : relever puis figer son digest après le premier
pull réussi ; aucun digest non vérifié n'est inventé dans cette livraison.
