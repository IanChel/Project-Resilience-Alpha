# Recette et livrables

## Définition du succès
Avant incident : un paiement confirmé, solde total 200000 et transaction stockée.
Pendant : charge provenant du second PC, paiement 503, métriques/journaux/score ML
visibles. Après : action autorisée sans correction humaine, politique active,
transaction de vérification inscrite et nouveau paiement confirmé. Garder la
charge active pendant le premier paiement rétabli pour exclure une simple fin
d'attaque comme explication du retour à la normale.

Le script acceptance.py observe et écrit une preuve PASS/FAIL. Son PASS exige
un nouveau dossier d'incident recovered, un 503 observé, une transaction finale
réussie et le total constant. Il n'atteste pas à lui seul l'origine second PC,
l'absence de correction humaine, le bon WAF ou la fidélité des horloges : ces
points demandent capture et observation du groupe.
Les timestamps d'observation ne constituent pas une mesure parfaite de RTO.
Conserver aussi les horodatages d'attaque et du moteur, synchronisés.

## Checklist de recette deux PC
- [ ] Pages manquantes 1/12 et 12/12 contrôlées, numéro de groupe renseigné.
- [ ] PA du groupe actif, Attaquant uniquement sur ce réseau, ports internes fermés.
- [ ] `docker compose config --quiet`, build et healthchecks vérifiés.
- [ ] SOPS chiffrer/déchiffrer vérifié sans affichage des clés.
- [ ] Login opérateur/loadbot, séparation des rôles et idempotence validés sur PostgreSQL.
- [ ] Requête WAF de test bloquée, audit réellement visible dans Loki.
- [ ] Prometheus fournit les quatre features, SOC affiche ses signaux.
- [ ] Baseline nominale collectée et report.json relu, modèle chargé.
- [ ] RAG répond à trois questions et cite des sources ; absence de privilèges d'action.
- [ ] Incident depuis Attaquant ; perturbation, score et alerte observés.
- [ ] Action Ansible et transaction de vérification visibles, paiement sous charge réussi.
- [ ] Trois essais répétés avec même version, résultats et échecs consignés.
- [ ] Restauration PostgreSQL testée et RTO/RPO mesurés.
- [ ] ZIP inspecté : aucune .secrets, aucun token, aucune clé privée.

## Preuve d'une reprise : champs de `runtime/evidence/acceptance-*.json`
`python scripts/acceptance.py` écrit, pour chaque exécution, ce qu'il faut citer dans le PCA/PRA. Les observations
brutes restent dans le fichier ; le bloc `summary` donne :

| Champ | Contenu |
|---|---|
| `incident.steps` | les quatre étapes, avec heure et décalage depuis la détection : `detected` (alerte du détecteur), `containing` (remédiation lancée), `verifying` (healthcheck OK), `recovered` (transaction témoin validée) |
| `incident.detection_to_recovered_s` | temps total détection → service rétabli, `within_target` face à 60 s : c'est le chrono du tableau de bord |
| `witness` | verdict de la transaction témoin (`validated`, `failed` ou `absent`), son identifiant et le total du registre |
| `user_visible_outage.seconds` | de la **première** indisponibilité vue par l'observateur (premier refus) à la première transaction réussie qui suit : c'est la définition du RTO de `08-PCA-PRA.md`. Ce n'est pas le même temps que le chrono (le service peut être utilisable avant que la reprise soit prouvée), au pas de 0,5 s |
| `ban` | le bannissement d'IP décidé, appliqué ou non (`06-SECURITE.md`, décision 1) |
| `detector_config` | `consecutive` et `nu` avec lesquels le détecteur tournait : sans eux une mesure n'est pas reproductible |
| `code_version` | commit et état modifié ou non de l'arbre de travail (trois essais « à version identique » : comparer les commits) |
| `complete`, `missing` | si la preuve est utilisable telle quelle, sinon ce qui manque |

Une preuve peut être `passed` et pourtant incomplète (par exemple sans la configuration du détecteur) :
ne citer dans le dossier que des preuves complètes. `python scripts/check_mercredi.py` le vérifie.

## Reset entre essais, jamais pendant le live
La politique reste activée après une reprise. Pour un nouvel essai, hors capture :
1. Arrêter le trafic offensif et conserver les preuves.
2. Supprimer uniquement le fichier de politique dans le conteneur :
   `docker compose exec payment python -c "from pathlib import Path; Path('/state/policy.json').unlink(missing_ok=True)"`
3. `docker compose restart payment` ; attendre /api/ready et le retour des métriques.
4. Attendre au moins 35s pour les fenêtres de télémétrie et le refroidissement.
5. Vérifier le paiement, puis lancer une nouvelle observation et une nouvelle attaque.
Les incidents historiques restent présents ; acceptance.py distingue les nouveaux.
Ne jamais utiliser `docker compose down -v` pour rétablir la démo : cela efface le registre.

## Dossier PDF — plan indicatif de dix pages
Nom exact `Workshop2026-M2-G2-Dossier.pdf`.
1. Mission, équipe, rôles et périmètre fictif.
2. Architecture et flux, implantation des postes.
3. Fonctionnement métier, authentification, transaction et idempotence.
4. Infrastructure et observabilité, preuves de collecte.
5. Données ML, entraînement, validation et résultats mesurés.
6. RAG local, modèle choisi, exemple sourcé et limites.
7. Scénario cyber, WAF/SOC/secrets et autorité de correction.
8. Chronologie et résultats des tests de reprise, y compris échecs.
9. EBIOS RM et analyse contextualisée NIS2/DORA.
10. PCA/PRA, arbitrages, risques résiduels et contributions.
Annexes ou liens dépôt : matrice, API, commandes, données/tests et empreintes.
Ce plan prépare le dossier ; aucun PDF final ni résultat de tests Docker inventé.

## PowerPoint — six diapositives
Nom exact `Workshop2026-M2-G2-Pres.pptx`.
1. Pourquoi le paiement doit reprendre et objectif de la démonstration.
2. Architecture et cinq responsabilités, schéma simple.
3. Scénario et chaîne détecter→agir→vérifier, politique d'autorisation.
4. Démonstration : dashboard, attaque et reprise observées.
5. Résultats chiffrés réels, RAG sourcé, limites et sécurité.
6. Risques, PCA/PRA, arbitrages et étape industrielle suivante.
Prévoir environ 5min présentation/live et 5min échange au jury local.

## Clip Chrono — <=60 secondes, capture continue
Nom exact `Workshop2026-M2-G2-VidChrono.mp4`.
Plan visé, à ajuster aux temps réellement mesurés :
- 0–7s : paiement initial réussi et état nominal.
- 7–12s : terminal du second PC qui lance le script autorisé.
- 12–25s : 503, features, score et alerte visibles.
- 25–43s : état containing/verifying, correction sans action humaine.
- 43–55s : transaction vérifiée et paiement manuel de contrôle réussi sous charge.
- 55–60s : identifiant transaction, intégrité et temps mesuré.

Le temps affiché à l'écran est le **chrono de reprise du tableau de bord** : il part de l'heure de
l'alerte posée par le détecteur et s'arrête à la transaction témoin validée. Il est calculé à partir
des étapes horodatées par le remédiateur (`stages` dans `/ops/status`) et de l'horloge du serveur,
jamais d'un compteur du navigateur. Les quatre étapes (détection, remédiation lancée, healthcheck OK,
transaction témoin) y sont listées avec leur heure, pour voir où passe le temps. Le filmer plutôt
qu'un chronomètre extérieur.
Si la chaîne prend plus de 60s, améliorer et remesurer ; ne pas couper ou accélérer
pour masquer l'attente ou une correction. Préinstaller, entraîner et ouvrir les
fenêtres avant capture est normal ; corriger pendant l'incident ne l'est pas.
Les sous-titres/titres peuvent expliquer la séquence sans en modifier la continuité.

## Archive finale
Dossier commun `Workshop2026-M2-G2/` avec les quatre rendus aux noms prescrits.
`python scripts/package.py` produit `Workshop2026-M2-G2-Code.zip`, contenant
sources/configs/tests/docs et un manifeste SHA256. Le numéro de groupe (2) est la
valeur par défaut du script ; `--group` ne sert qu'à le surcharger.
Joindre séparément les preuves réelles relues et anonymisées, sans identifiants
secrets, après recette. La vidéo doit être capturée sur vos postes ; elle n'est
pas remplacée par une animation ou un enregistrement fabriqué.
