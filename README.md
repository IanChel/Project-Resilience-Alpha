# RESILIENCE-ALPHA — prototype de paiement et reprise autonome

Workshop EPSI BAC+5, octobre 2026. Environnement entièrement fictif et limité
au laboratoire du groupe. Version initiale préparée à partir des pages 2 à 11/12
du sujet ; les pages 1 et 12 restent à contrôler.

## Commencer
1. Lire `docs/01-EXIGENCES.md` : 37 exigences, sources et critères de preuve.
2. Fixer l'architecture avec le coach : `docs/02-ARCHITECTURE.md`.
3. Attribuer les cinq domaines et l'ordre des travaux : `docs/04-PLAN-EQUIPE.md`.
4. Installer sur Windows/WSL : **`docs/INSTALL.md`**.
5. Vérifier les résultats réellement exécutés : **`docs/VALIDATION.md`**.

## Chaîne visée
Transaction confirmée → charge de devis bornée depuis second PC → paiement
perturbé → détection ML sur métriques et logs → alerte authentifiée → playbook
Ansible active une admission ciblée → transaction vérifiée par le WAF → paiement
réussi sous charge. Aucun conteneur n'est administré par le RAG et aucun socket
Docker n'est confié au moteur de remédiation.

## Composants livrés
- Authentification FastAPI et rôles alice/loadbot, API paiement et registre atomique.
- PostgreSQL au déploiement ; SQLite uniquement pour tests natifs.
- React/Tailwind : paiement, états ML, chronologie des incidents, RAG.
- Compose, Ansible, WAF ModSecurity/CRS, Prometheus/Grafana/Loki et collecte Alloy.
- ML OneClassSVM, entraînement sur baseline réelle à collecter, alertes signées.
- RAG documentaire local avec LangChain/Ollama qwen2.5:1.5b et sources retournées.
- SOC intégré minimal, SOPS/age, scripts de sauvegarde/restauration et recette.
- Analyse EBIOS, NIS2/DORA et PCA/PRA ; plans PDF/PPTX/Clip Chrono.

## Arborescence
`services/` code Python ; `frontend/` React ; `infra/` configurations et playbooks ;
`scripts/` installation des secrets, trafic et recette ; `tests/` tests unitaires
et intégration native ; `docs/` architecture, contrats, procédure et gouvernance ;
`evidence/` résultats des vérifications réalisées ici.

## Tests locaux
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
Le test d'intégration native lance des serveurs HTTP sur loopback et exécute
réellement Ansible. Il emploie SQLite, un proxy de test et un modèle entraîné sur
fixture synthétique ; ce n'est pas la recette Docker/deux PC.
Sous Windows, exécuter ces tests dans WSL pour Ansible et les outils Linux.

## Commandes de déploiement, après prérequis SOPS/age
```bash
python scripts/init_secrets.py
docker compose config --quiet
python -m ansible.cli.playbook -i localhost, infra/ansible/deploy.yml
docker compose exec ollama ollama pull qwen2.5:1.5b
```
L'installation complète, le hotspot et l'entraînement sont détaillés dans INSTALL.
Jalon de lundi, une fois la stack levée : `python scripts/check_lundi.py` constate en
lecture seule les 5 conteneurs, `/health`, `/metrics`, la cible Prometheus et la
datasource Grafana (code 0 si tout est OK, 1 sinon) ; il ne démarre ni ne modifie rien.
Jalon critique de mardi, après avoir lancé l'attaque à la main : `python scripts/check_mardi.py
--last 120` mesure le pic dans Prometheus et l'`anomaly=true` du détecteur sur cette fenêtre
et écrit une preuve horodatée dans `runtime/evidence/` (lecture seule, code 0 ou 1).
La commande d'attaque se lance exclusivement sur le second PC autorisé.
Un état ML « waiting_for_trained_model » et un RAG 503 sont explicites tant que
baseline/modèle ne sont pas installés ; aucune réussite n'est simulée à l'écran.

## Livrables
`docs/09-RECETTE-RENDU.md` prépare dossier PDF, slides, vidéo continue <=60s et ZIP.
Le PDF et le PPTX finaux doivent intégrer vos résultats réels ; la vidéo doit être
capturée sur vos machines. Ils ne sont pas inclus sous forme de faux rendus terminés.
Créer l'archive sans secrets : `python scripts/package.py --group 3` (vrai numéro).

Ce prototype n'est pas une plateforme bancaire de production, une preuve de
conformité ou un système de haute disponibilité. Les écarts sont détaillés dans
les documents de sécurité, gouvernance et PCA/PRA.
