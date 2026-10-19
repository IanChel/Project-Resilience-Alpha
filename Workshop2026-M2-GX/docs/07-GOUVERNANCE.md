# Gouvernance — analyse adaptée au démonstrateur

Document pédagogique, à valider avec le groupe et le coach. Les choix sont reliés
à ce qui peut être démontré. Aucun avis de conformité juridique ou certificat.

## Hypothèses d'activité
Entreprise financière fictive ALPHA PAY, un marchand fictif et un opérateur.
La fonction critique est le traitement fiable d'une transaction. Impact d'une
interruption : demandes retardées, perte de confiance et charge d'exploitation.
Aucun chiffre financier réel fourni. Hypothèse illustrative à discuter :
10 transactions/min × marge fictive 0,10 EUR = 1 EUR/min de contribution différée,
ce qui n'est pas nécessairement une perte définitive. Ajouter le coût fictif du
support et distinguer report d'opérations, pertes et coût de réputation.

## EBIOS RM : synthèse des cinq ateliers
### 1. Cadrage et socle
Périmètre : PC Hôte, PA groupe, PC Attaquant autorisé, services de paiement,
registre, observabilité, automate et assistant. Actifs essentiels : disponibilité
du paiement, intégrité du registre et confiance dans les décisions de reprise.
Biens supports : DB, clés, images, poste Hôte, procédures et réseau.
Événements redoutés : paiement indisponible, double débit, fuite de secrets,
remédiation abusive, perte du registre. Échelle gravité 1 faible à 4 critique.
Socle : contrôle accès, secrets chiffrés, WAF, réseaux internes, audit et tests.
### 2. Sources de risque et objectifs visés
Acteur malveillant sur le laboratoire, testeur à rôle loadbot et opérateur
négligent ; objectifs : perturber le paiement, abuser du contrôle, altérer les
transactions. Les pannes accidentelles complètent l'analyse de continuité,
mais ne sont pas confondues avec des couples source de risque/objectif malveillant.
### 3. Scénarios stratégiques et écosystème
S1 : client autorisé abuse du devis pour rendre le paiement indisponible.
S2 : composant applicatif compromis vise les secrets pour obtenir du contrôle.
S3 : poste Hôte compromis compromet les services et les preuves locales.
Parties prenantes : opérateur, marchand, responsable technique, coach ; fournisseurs
logiciels Docker, images et modèle local. L'école et ses réseaux sont hors cible.
### 4. Scénarios opérationnels
S1 : login loadbot → requêtes devis répétées → occupation capacité → 503 paiements.
S2 : accès à un composant → recherche de secret → fausse alerte ou contrôle ;
barrières : secrets par service, signature/fraîcheur/déduplication, action fixe.
S3 : compromission Hôte → altération des volumes/logs ; non couvert par ce prototype.
### 5. Traitement et risques résiduels
Matrice qualitative (vraisemblance et gravité 1–4, produit indicatif pour prioriser ;
cette multiplication est un outil de travail, pas un score EBIOS officiel).

| Risque | Initial V×G | Traitement et preuve | Résiduel V×G | Décision |
|---|---|---|---|---|
| Indisponibilité devis/paiement | 4×3=12 | ML + admission + transaction de vérification | 2×3=6 | Accepté pour démo ; séparer capacités ensuite |
| Double débit lors d'un retry | 3×4=12 | Transaction DB, verrou, idempotence ; test concurrent | 1×4=4 | Validation PostgreSQL supplémentaire exigée |
| Abus de remédiation | 3×4=12 | HMAC, horodatage, action fixe, sans socket | 1×4=4 | Tester alertes forgées et redémarrage |
| Secrets présents dans livrables | 3×4=12 | SOPS/age, exclusion ZIP, revue manifeste | 1×4=4 | Vérifier l'archive finale |
| Instruction malveillante RAG | 3×3=9 | Corpus contrôlé, aucun outil ni clé d'action | 2×2=4 | Réponse erronée possible ; vérification humaine |
| Perte du PC Hôte | 2×4=8 | Backup chiffré et copie externe à organiser | 2×4=8 tant que copie absente | Explicitement non résolu par la démo |
| Logs/ML indisponibles | 2×3=6 | État d'erreur explicite ; pas de fausse reprise | 2×3=6 | Prévoir alerte externe et supervision de secours |

Responsables, échéances, acceptation du risque et résultats effectifs à compléter.

## NIS2 et DORA : pertinence, preuves et écarts
Références primaires : directive (UE) 2022/2555 (NIS2), notamment articles 4,
20, 21 et 23 ; règlement (UE) 2022/2554 (DORA), notamment gestion des risques TIC,
incidents, tests de résilience et risques de prestataires. DORA s'applique depuis
le 17 janvier 2025 (art.64). L'assujettissement d'une véritable entité dépend de
sa qualification et du cadre applicable. Ne pas supposer que toutes les obligations
NIS2 et DORA s'additionnent : NIS2 art.4 prévoit le rôle des textes sectoriels.
La société fictive ne permet pas de conclure à un statut réglementaire réel.

| Thème pertinent | Réponse prototype / preuve attendue | Écart industriel |
|---|---|---|
| Gouvernance du risque TIC | EBIOS synthétique, responsable par domaine, décisions tracées | Validation direction, politique et contrôles indépendants |
| Gestion d'incident | Détection, timeline, action autorisée, état recovered/failed | Qualification réglementaire et procédure formelle de notification |
| Continuité et restauration | Objectifs RTO/RPO, backup et tests métier | Sites indépendants, exercices réguliers, sauvegardes hors machine |
| Tests de résilience | Scénario borné, tests automatisés, preuves de reprise | Programme de tests proportionné et exigences applicables aux entités |
| Accès et secrets | Sessions, rôles, SOPS, contrôle interne | MFA, IAM complet, rotation et revue régulière des droits |
| Prestataires TIC | Inventaire images/modèle et dépendances | Due diligence, contrats, registre réglementaire et stratégie de sortie |
| Signalement | Journal d'incident pédagogique | Aucun signalement réel effectué ; rôles, seuils et délais à valider selon régime |

Ne pas écrire « plateforme conforme NIS2/DORA ». Écrire : « démonstrateur aligné
sur des thèmes de résilience, avec écarts identifiés ». Les obligations de
notification ne sont pas démontrables par un simple webhook interne.

## Arbitrages présentables à une direction
Prioriser la reprise du paiement et l'intégrité avant les fonctionnalités UI.
Limiter l'autorité de l'automate plutôt que lui confier l'administration du Hôte.
Choisir un LLM 1.5B et un SOC intégré pour respecter les ressources disponibles.
Accepter le point de défaillance Hôte pour quatre jours en le signalant clairement.
Investissement suivant : séparation des capacités, TLS/IAM, sauvegardes hors site,
validation de la chaîne d'approvisionnement et mesure sur plusieurs incidents.

Sources officielles consultées le 19/10/2026 :
- https://cyber.gouv.fr/securisation/analyse-des-risques/methode-ebios-rm/
- https://eur-lex.europa.eu/eli/dir/2022/2555/oj/eng
- https://eur-lex.europa.eu/eli/reg/2022/2554/oj/eng
