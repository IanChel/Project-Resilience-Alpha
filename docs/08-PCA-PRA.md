# PCA/PRA du prototype

## Objectifs et périmètre
Fonction prioritaire : paiement fictif exact et traçable.
RTO cible pour l'incident de capacité : 45 secondes depuis la première
indisponibilité observée jusqu'à une transaction confirmée. C'est une cible à
mesurer, pas un résultat obtenu sur les PC de l'équipe.
RPO cible sur ce scénario sans destruction de DB : 0 transaction déjà confirmée
perdue. La limitation ne réinitialise ni comptes ni données.
Pour la perte de DB/Hôte, le RPO dépend du dernier backup réellement disponible.
Aucune fréquence de sauvegarde n'est supposée acquise dans cette livraison.

## PCA pendant incident
Le dashboard affiche l'erreur et l'avancement, le client ne prétend pas qu'une
transaction rejetée est réussie. Ne pas contourner l'API ni modifier le registre.
Une demande au résultat incertain est rejouée avec sa clé d'idempotence.
Pendant la démonstration, aucune intervention corrective humaine n'est permise :
si l'automate échoue, conserver les traces et constater l'échec. L'analyse et le
reset manuel se font ensuite, entre deux essais.

## Reprise automatique couverte
1. Mesures et journaux révèlent la pression.
2. Le ML produit des observations anormales d'affilée, chacune confirmée par des rejets
   de capacité : trois par défaut, réglable par `DETECTOR_CONSECUTIVE` (docs/05-ML-RAG.md).
3. Une alerte signée est acceptée et tracée.
4. Ansible active l'admission fixe, idempotente et persistée sur volume.
5. Une vérification de disponibilité DB ne suffit pas : le moteur crée un paiement
   d'un centime par le WAF, vérifie son enregistrement et le total constant.
6. État recovered uniquement si toutes les vérifications réussissent.
7. Un échec passe en failed, avec demande de revue, sans boucle de commandes ouverte.

## Sauvegarde et restauration de la base (hors live)
`scripts/backup.py` crée un pg_dump custom dans runtime/backups sans mot de passe
en argument. La connexion locale au conteneur utilise le rôle payments.
La copie reste sur Hôte : copier vers un support distinct chiffré pour couvrir
sa perte ; ne pas transporter les clés privées avec les sauvegardes.

Procédure de restauration destructive de laboratoire :
1. Identifier la sauvegarde, vérifier son hash et conserver les traces de panne.
2. Hors démonstration, exécuter `python scripts/restore.py chemin.dump --confirm-lab-restore`.
3. Le script arrête l'API, restaure, puis redémarre l'API ; il ne supprime pas les volumes.
4. Vérifier /api/ready puis exécuter une transaction et comparer le registre attendu.
5. Mesurer le délai et la perte éventuelle depuis la date du backup ; consigner le résultat.
La restauration Docker/PostgreSQL est fournie mais n'a pas été exécutée ici.

## Responsabilités
B pilote la reprise infrastructure et les sauvegardes ; A vérifie registre et API ;
C vérifie la disponibilité des mesures/modèle ; D contrôle périmètre/secrets et
préserve les traces ; E tient la chronologie et valide l'écart aux objectifs.
Une altération des données, une fuite ou une compromission nécessite confinement,
investigation et rotation éventuelle : un simple retour du paiement ne la résout pas.

## Tests de résilience et limites
À réaliser : incident principal trois fois, restart payment avec politique conservée,
restart remediator pendant containing, indisponibilité Loki/Prometheus, clé d'alerte
invalide, DB indisponible, restauration backup sur base de test.
Le `restart: unless-stopped` de Docker n'est pas une preuve de remédiation IA.
Pas de bascule Hôte, pas de restauration automatique de données compromises,
pas de continuité de service si Docker Desktop ou Windows s'arrête.
