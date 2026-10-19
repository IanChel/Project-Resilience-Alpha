# Analyse du cahier des charges — RESILIENCE-ALPHA

Version du 19 octobre 2026. Matrice établie d'abord à partir de dix photographies
(pages imprimées 2 à 11/12), puis **contrôlée sur le sujet complet en PDF**, présent à
la racine du poste (non versionné, et exclu de l'archive de rendu). Les pages 1 et 12, qui manquaient, ont été lues : page 1 page de
couverture, page 12 glossaire (AIOps, ML, IaC, Red/Blue Team, WAF, SIEM, EBIOS RM,
NIS2, DORA, PCA/PRA, Zero-Touch Recovery). **Elles n'ajoutent aucune exigence** : la
matrice des 37 lignes est complète. Les numéros p. désignent les pages imprimées.

Le résultat demandé est une chaîne exécutée sur les machines de l'équipe :
transaction avant incident, attaque depuis un second PC, collecte, détection,
décision et correction sans intervention humaine, puis transaction confirmée.
Un simple redémarrage de conteneur ne démontre pas cette reprise.

| ID | Obligation / choix autorisé | Source | Réponse proposée | Preuve et critère de recette |
|---|---|---|---|---|
| E01 | Cinq domaines présents quelle que soit l'équipe | p.2–5 | DEV, INFRA, IA/DATA, CYBER, gouvernance | Démonstration et contribution attribuée pour chacun |
| E02 | SI et données entièrement fictifs | p.3 | Deux comptes alice/merchant, centimes simulés | Aucun numéro bancaire ou donnée réelle |
| E03 | Microservices : DB, API métier, authentification, frontal | p.4 | PostgreSQL, FastAPI auth/payment, React | Transaction persistée via interface authentifiée |
| E04 | API parmi Node.js, Python/FastAPI ou Go | p.4 | Python/FastAPI | OpenAPI des services et tests API |
| E05 | Tableau de bord React et Tailwind CSS | p.4 | frontend/ | Build React ; état ML/incidents et paiement visibles |
| E06 | Docker Compose | p.4 | compose.yaml | Configuration validée puis démarrage sur un autre PC |
| E07 | Playbooks Ansible, rôle expliqué | p.4,7 | Déploiement local WSL + remédiation uri | Journaux Ansible et opération idempotente |
| E08 | Prometheus / Grafana / Loki réellement utilisés | p.4 | Métriques, dashboards provisionnés, logs Alloy | Mesures et logs présents avant/pendant/après |
| E09 | Détection ML ; pas seulement règles en dur | p.5 | StandardScaler + OneClassSVM | Baseline réelle, artefact entraîné, scores et limites |
| E10 | Modèle ML raccordé supervision et reprise | p.5 | Prometheus/Loki → detector → alerte signée | Incident horodaté, score et action corrélés |
| E11 | Documenter données, préparation, modèle, résultats et limites | p.5 | baseline.json, report.json, procédure ML | Rapport généré, FPR et tests d'attaque consignés |
| E12 | RAG local Ollama + LangChain | p.5 | Recherche TF-IDF documentaire + ChatOllama | Question technique → réponse avec extraits sourcés |
| E13 | LLM au maximum 8 milliards de paramètres | p.5 | qwen2.5:1.5b | Vérifier `ollama show qwen2.5:1.5b` et relever modèle |
| E14 | Assistant séparé de l'automate et privilèges maîtrisés | p.5 | RAG sans outil, secret control absent | Aucun accès RAG au moteur d'action, lecture seule |
| E15 | Au moins une attaque réelle, reproductible, depuis PC distinct | p.3,5–6 | Charge de devis bornée depuis PC Attaquant | Capture second poste + 503 et traces réels |
| E16 | Défenses : durcissement accès et composants | p.5 | Secrets ciblés, réseaux internes, non-root apps | Tests d'accès ; aucun socket Docker ; DB non publiée |
| E17 | Filtrage WAF | p.5 | ModSecurity + OWASP CRS | Requête de test bloquée, audit présent dans Loki |
| E18 | SIEM OU fonction SOC intégrée | p.5 | SOC minimal : règles temporelles Loki et signaux | Règles auth/pression/WAF et timeline Grafana |
| E19 | Secrets avec HashiCorp Vault OU SOPS | p.5 | SOPS + age ; mounts Compose au runtime | Chiffrement/déchiffrement testé sur poste, aucune clé archivée |
| E20 | Remédiation autonome et vérification métier | p.3–5 | Playbook fixe active admission ; transaction par WAF | HTTP 200, transaction inscrite, total constant |
| E21 | PC Hôte Windows Docker Desktop WSL2 | p.6 | Ubuntu WSL, conteneurs Linux | Relever configuration, versions et ressources |
| E22 | PC Attaquant distinct ; aucun composant défensif dessus | p.6 | Python/httpx seulement pour le scénario | Inventaire des deux postes |
| E23 | PC IA optionnel, uniquement Ollama/API | p.6 | Variante documentée, RAG reste sur Hôte | Accès restreint à l'IP Hôte, aucun port public |
| E24 | Point d'accès mobile Windows imposé | p.6 | RESILIENCE-G2, 192.168.137.0/24 | Hôte .1, Attaquant connecté uniquement au PA |
| E25 | Aucune attaque campus, autre groupe ou Internet | p.5–6,11 | Cible paramétrable mais **bornée au sous-réseau du lab** : tout autre hôte refusé avant connexion ; `--lab-authorized` obligatoire | Garde-fou testé (`tests/test_configs.py`) ; vérifier route et pare-feu avant l'exercice |
| E26 | Analyse EBIOS Risk Manager | p.5,7 | Cadrage et cinq ateliers synthétiques | Scénarios reliés aux composants et arbitrages |
| E27 | Analyse NIS2/DORA contextualisée | p.5 | Table exigences/preuves/écarts | Aucun label de conformité industrielle inventé |
| E28 | PCA/PRA : objectifs, rôles, risques résiduels | p.5 | RTO/RPO cibles, restauration et vérifications | Mesures effectives et test de restauration à joindre |
| E29 | Tests et démonstration reproductibles | p.4,7–8 | pytest + procédure deux PC + observateur | Preuves avec résultat explicite PASS/FAIL |
| E30 | Dossier PDF, architecture/flux/risques/résultats/contributions | p.8 | Plan 10 pages + annexes | 8–12 pages indicatives, contenu contextualisé |
| E31 | Support Pres.pptx | p.8 | Plan 6 slides | Cohérent avec les mesures réellement obtenues |
| E32 | Clip Chrono MP4 <=60s, séquence continue | p.8 | Storyboard et recette chronométrée | Pas de coupe masquant une correction manuelle |
| E33 | Archive Code.zip structurée + README, tests, API, scripts | p.8 | scripts/package.py et manifeste SHA256 | Déploiement expliqué, aucun secret en clair |
| E34 | Noms de fichiers imposés et dossier commun | p.8 | **Groupe 2**, noms figés : `Workshop2026-M2-G2-Dossier.pdf`, `-Pres.pptx`, `-VidChrono.mp4`, `-Code.zip` dans `Workshop2026-M2-G2/` ; `package.py` utilise 2 par défaut | Quatre noms exacts validés avant remise |
| E35 | Gel jeudi 17h, remise avant 23h59 | p.7 | Planning et préparation preuves | Aucun développement pendant soutenance vendredi |
| E36 | Groupe normalement 5, 4/6 sur autorisation coach | p.4 | Répartition 5 responsables, adaptable | Coach valide répartition et architecture |
| E37 | Usage IA permis ; responsabilité humaine de vérification | p.7 | Statuts de validation explicites | Chacun sait expliquer ses composants et ses choix |

## Ce qui reste un choix de conception
PostgreSQL plutôt qu'une autre DB, FastAPI parmi les langages proposés,
OneClassSVM parmi les modèles ML, SOPS plutôt que Vault, fonction SOC intégrée
plutôt qu'un SIEM complet, modèle local 1.5B plutôt que 8B, attaque de capacité
applicative plutôt qu'injection/exfiltration. Ces choix ne sont pas des obligations
ajoutées au sujet. L'utilisation d'Elastic Stack n'est pas attendue (p.4).

## Priorité de notation
Jury local : reprise autonome en direct 5/20 ; expertise/cohérence 4/20 ;
Clip Chrono/dashboard 4/20 ; gouvernance/pitch 4/20 ; dossier/réponses 3/20.
Une intervention corrective humaine pendant le live entraîne 0/5 sur l'axe reprise.
Passage local 10 minutes : 5 de présentation/démonstration + 5 d'échange.
Finale nationale, si sélection : 5 minutes, introduction individuelle en anglais,
Clip Chrono, puis live ; grille technique sur 70 points (p.10).
