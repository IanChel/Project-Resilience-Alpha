# État de la semaine — 2026-10-19

Statuts : `FAIT` · `PARTIEL` · `RUNTIME` (le code existe, la preuve exige la stack allumée) · `DIVERGENT ASSUMÉ`
(écart au plan, justifié par écrit) · `HORS-REPO`. Suite de tests : 244 réussis, 1 échec (`test_native_chain`,
Ansible est impossible sous Windows ; à passer sous Linux).

| ID | Carte | Statut | Preuve | Bloquant pour |
|---|---|---|---|---|
| L1 | Squelette API FastAPI | FAIT | `services/payment/main.py`, spec conforme (test) | — |
| L2 | React + Tailwind | FAIT | `frontend/src/`, build Vite réel vérifié | — |
| L3 | `docker compose up` | RUNTIME | `compose.yaml`, jamais démarré ; `check_lundi.py` | tout le runtime : M5, M7, W1, W7 |
| L4 | PC Attaquant, scénario DoS | PARTIEL | `scripts/attack_lab.py`, `docs/04-ATTAQUE.md` ; poste et validation du coach hors dépôt | M4, M7 |
| L5 | Baseline + modèle | DIVERGENT ASSUMÉ | OneClassSVM (`docs/05`, D-07) ; baseline et modèle non produits | M5, M7 : sans modèle, aucune détection |
| L6 | 4 contrats + EBIOS + Kanban | FAIT | 5 specs validées contre de vraies réponses ; EBIOS et Kanban hors dépôt | — |
| L7 | Sync lundi | RUNTIME | `check_lundi.py`, jamais exécuté | tout |
| M1 | API complète + auth | DIVERGENT ASSUMÉ | persistance et rôles OK ; jeton HMAC, pas JWT (`docs/06`, décision 3) ; budget de connexion découplé | — |
| M2 | Front paiement | PARTIEL | appel réel de `/api/payments` ; 2 écarts d'affichage non corrigés (bandeau d'erreur jamais effacé, réponse non JSON) | lisibilité devant le jury |
| M3 | Ansible + `/metrics` | PARTIEL | playbooks vérifiés statiquement seulement ; série `quotes/200` créée au 1ᵉʳ devis (`payment/main.py:87`) | M7, W1 : détecteur aveugle au repos |
| M4 | Attaque reproductible | RUNTIME | script déterministe ; le 2ᵉ lancement exige de réinitialiser le confinement (`docs/09`) | M7, J1 |
| M5 | Modèle + `/anomaly` + seuil | RUNTIME | `/anomaly`, `calibrate_detector.py`, cible chiffrée (`docs/05`) ; seuil jamais mesuré sur de vraies données | M7 |
| M6 | NIS2/DORA + PCA/PRA | HORS-REPO | `docs/07`, `08` (affirmations factuelles corrigées) ; le contenu est à P6 | J5 |
| M7 | Jalon critique | RUNTIME | `check_mardi.py` | W7, J1 |
| W1 | Moteur de remédiation | DIVERGENT ASSUMÉ | 6 items sur 8 faits, recréation écartée (`06`, déc. 2), ban au WAF en surcouche non vérifiée (déc. 1) ; Ansible jamais exécuté en conteneur | W7, J1, le live |
| W2 | Chrono du dashboard | RUNTIME | `Chrono.jsx`, étapes horodatées côté backend, 12 tests ; jamais vu en direct | le clip, le live |
| W3 | Transaction témoin | FAIT | `remediator/main.py`, 6 tests dont un ban actif | — |
| W4 | WAF, SIEM, secrets | PARTIEL | corrélation par incident, secrets testés ; ban au WAF non vérifié ; aucune limite de débit au WAF (`06`) | un ban visible au live |
| W5 | RAG | DIVERGENT ASSUMÉ | TF-IDF (`docs/05`, D-08), 503 testé, encodage corrigé ; génération non vérifiée sans Ollama | la démo du RAG |
| W6 | Restauration chronométrée | RUNTIME | `acceptance.py` (preuve complète) ; `backup.py`, `restore.py` jamais exécutés | J5 (PRA) |
| W7 | Sync mercredi, 60 s | RUNTIME | `check_mercredi.py` ; ne se clôt pas sans stack | J1, J9 |

## Prêt pour le gel de jeudi 17h ?
**Non.** Rien n'a encore tourné de bout en bout, donc aucune des conditions de la semaine n'est prouvée. Manque :
la stack démarrée une fois (`check_lundi.py`) ; la baseline et le modèle ; une attaque réelle (`check_mardi.py`) ;
la boucle chronométrée (`acceptance.py` puis `check_mercredi.py`) ; Ansible exécuté **dans le conteneur** du
remédiateur ; la suite complète sous Linux, avec le test natif et le registre sur PostgreSQL ; et, hors dépôt, le
dossier PDF, le support, le clip (3 prises), l'archive et l'EBIOS. `run-demo.sh` (carte J3) n'existe pas.

## Risques pour la note
Par gravité, en commençant par ce qui peut forcer une intervention manuelle pendant le live (0/5).
1. **Ansible jamais exécuté dans le conteneur** du remédiateur (non-root, système de fichiers en lecture seule) : un échec
   donne `failed` avec `manual_review_required`. À tester à froid avant tout.
2. **Détecteur aveugle** tant qu'aucun devis n'a été émis depuis le démarrage de `payment`. Le reset documenté
   (`docs/09`) redémarre `payment` : sans devis préalable, pas de mesure, donc pas de remédiation autonome.
3. **Reset manuel entre essais** : le confinement persiste, un 2ᵉ passage ne produit ni 503 ni incident.
4. Faux positifs jamais mesurés sur la vraie baseline (17 % du modèle seul sur données synthétiques, filtré en
   pratique par la barrière de capacité) : une remédiation sans attaque serait vue du jury.
5. Un flot de connexions publiques peut verrouiller le login des opérateurs : se connecter avant l'attaque.
6. Le ban d'IP peut ne rien faire (adresse vue par le WAF sous Docker Desktop, 3 hypothèses sur l'image) ; sans danger,
   mais il ne serait pas démontré.
7. La transaction témoin passe par le WAF réel : jamais testée contre ses règles CRS.
8. Chrono et corrélation jamais vus avec de vraies données ; bandeau d'erreur périmé sur le dashboard.
9. RAG : une question hors sujet n'est pas écartée à la récupération (`docs/05`, limites mesurées).

## Dette assumée
Antisèche pour les questions du jury : où se trouve la justification de chaque écart.

| Écart | Justification |
|---|---|
| OneClassSVM plutôt qu'IsolationForest | `docs/05-ML-RAG.md`, décision D-07 |
| Jeton HMAC maison plutôt que JWT | `docs/06-SECURITE.md`, décision 3 (rédigée à partir du code, à valider) |
| On ne recrée pas le conteneur : admission + ban | `docs/06-SECURITE.md`, décision 2 |
| Ban d'IP en surcouche optionnelle, non vérifiée | `docs/06-SECURITE.md`, décision 1 |
| TF-IDF plutôt que ChromaDB | `docs/05-ML-RAG.md`, décision D-08 |
| Limitation de débit applicative, pas au WAF | `docs/06-SECURITE.md`, « Limitation de débit » |
| Budget de connexion partagé, remédiateur avec le compte `alice` | `docs/06-SECURITE.md`, « Budget de connexion » |
| Le RAG détient `session_key` | `docs/07-GOUVERNANCE.md`, tableau des risques |
| TLS, OIDC, haute disponibilité absents | `docs/06-SECURITE.md`, « Écarts avant tout usage industriel » |
