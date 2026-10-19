# Répartition et ordre de développement

Base : cinq membres, conformément au sujet ; remplacer les responsables A–E par
les prénoms et conserver les commits/PR ou un journal des contributions.
Hafsa peut prendre C (IA/Data), avec B pour les métriques et A pour les API.
Les domaines restent obligatoires même si aucun membre n'a la spécialité.

| Responsable | Domaine | Livrable principal | Interface à convenir dès lundi |
|---|---|---|---|
| A | DEV / intégration | Auth, registre, API, React | Routes, erreurs, idempotence et événements |
| B | INFRA | Compose, Ansible, Prometheus/Grafana/Loki | Noms DNS, volumes, ports, métriques |
| C | IA / DATA | Baseline réelle, ML, RAG local | Vecteur 4 features, score, alerte HMAC |
| D | CYBER | PA, WAF, SOC, SOPS, attaque bornée | Périmètre, accès, traces et action autorisée |
| E | Gouvernance / recette | EBIOS, NIS2/DORA, PCA/PRA, preuves | RTO/RPO, critères de recette et arbitrages |

Aucune personne ne porte seule la démonstration : chaque binôme teste l'interface
qu'il fournit à l'autre. E collecte les preuves au fur et à mesure.
À quatre, partager la gouvernance entre tous avec un pilote ; à six, séparer
frontend/recette de l'API. Valider la composition avec le coach.

| Jour | Ordre et objectif | Validation de fin de journée |
|---|---|---|
| Lundi | Lire exigences ; vérifier matériel/PA ; attribuer domaines ; choisir scénario ; fixer API et risques ; démarrer DB/auth/API et premier paiement | Architecture et EBIOS cadrés avec coach ; paiement persistant |
| Mardi | Construire React ; déployer Compose/Ansible ; remonter logs/métriques ; générer secrets SOPS ; activer WAF ; produire trafic normal et entraîner ML ; préparer RAG et scénario | Stack installable ; baseline enregistrée ; endpoint contrôle idempotent |
| Mercredi | Relier ML→alerte→Ansible→vérification métier ; tester depuis PC Attaquant ; afficher timeline ; tester questions RAG ; mesurer reprise | Au moins une chaîne complète vérifiée, preuves sauvegardées |
| Jeudi matin | Tests d'échec, rejouabilité, arrêt de service et restauration ; risques résiduels ; mesures finales | Trois répétitions du scénario avec même version |
| Jeudi après-midi | Enregistrer Clip continu <=60s ; finaliser dossier et slides ; vérifier noms et ZIP | Gel 17h ; rendu avant 23h59 |
| Vendredi | Soutenance, sans poursuivre le développement | Démonstration autonome et explication par chaque membre |

## Chemin critique
1. Auth + transfert atomique et transaction persistée.
2. Compose + PA + accès depuis second PC.
3. Métriques/logs réels + baseline propre.
4. Détection + action fixe + vérification métier.
5. Tableau de bord et scénario continu.
6. RAG et preuves de sécurité, gouvernance, répétitions et rendus.
Le RAG et la gouvernance avancent en parallèle dès que les interfaces sont fixées.
Aucun pilier n'est optionnel ; si le matériel manque, réduire le modèle ou employer
le PC IA autorisé, pas supprimer le RAG ou la supervision.
