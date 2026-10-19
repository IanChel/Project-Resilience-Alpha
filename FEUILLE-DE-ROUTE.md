# Feuille de route — RESILIENCE-ALPHA, groupe 2

Ce qui reste pour un projet **100 % opérationnel**. On coche au fur et à mesure (`- [ ]` → `- [x]`).

> **Où on en est.** Le code est quasiment complet : 246 tests passent, les 5 piliers du sujet sont couverts.
> Mais **la stack n'a jamais démarré**. L'écart qui reste n'est pas du développement, c'est de l'exécution.
> Toutes les cases de la phase 0 à la phase 3 se font **dans l'ordre** : chacune débloque la suivante.

Échéances fixes : **gel du code jeudi 17h00** · **remise jeudi 23h59** · **soutenance vendredi matin**.

---

## Phase 0 — Démarrer (bloquant pour tout le reste) · P3 + P4

- [ ] **0.1** Prérequis sur le PC Hôte : Docker Desktop + WSL2 actifs, `sops` et `age` installés dans WSL
      → `sops --version && age-keygen --version && docker compose version`
- [ ] **0.2** Générer les secrets · `python scripts/init_secrets.py`
      *Fait quand* : `.secrets/runtime/` contient les 7 fichiers. **Ne jamais commiter ce dossier** (déjà ignoré).
- [ ] **0.3** Démarrer la stack · `docker compose up -d --build`
      Le `--build` est obligatoire : les images embarquent le code modifié cette semaine.
- [ ] **0.4** Valider le jalon de lundi · `python scripts/check_lundi.py`
      *Fait quand* : 5/5 OK (conteneurs Up, `/health`, séries `lab_*`, cible Prometheus, datasource Grafana).
- [ ] **0.5** 🔴 **RISQUE N°1 — Tester Ansible DANS le conteneur du remédiateur**
      `docker compose exec remediator python -m ansible.cli.playbook -i localhost, infra/ansible/contain.yml --syntax-check`
      Le conteneur tourne non-root avec un système de fichiers en lecture seule. **Si Ansible n'y démarre pas,
      chaque incident finit en `failed` + `manual_review_required` = le scénario à 0/5 de vendredi.**
      *Fait quand* : la commande sort en code 0. Si elle échoue, **tout s'arrête ici** et on corrige d'abord.

## Phase 1 — Rendre la détection possible · P5

- [ ] **1.1** Arbitrage à trancher : pré-créer la série `lab_requests_total{route="quotes"}` au démarrage de
      `payment` (1 ligne) **ou** s'astreindre à émettre un devis avant chaque contrôle.
      *Pourquoi* : tant qu'aucun devis n'a été émis, le détecteur reste en `telemetry_or_delivery_error`.
      Et la procédure de reset entre essais redémarre justement `payment`.
- [ ] **1.2** Générer du trafic normal · `python scripts/normal_traffic.py --seconds 240` (terminal A)
- [ ] **1.3** Collecter la baseline (terminal B, ~15 s après)
      `docker compose exec detector python -m services.detector.collect_baseline`
- [ ] **1.4** Entraîner le modèle · `docker compose exec detector python -m services.detector.train`
      *Fait quand* : `/ops/ml` sort de `waiting_for_trained_model` et passe à `monitoring`.
- [ ] **1.5** Relever le taux de faux positifs dans `report.json` et le consigner.

## Phase 2 — Monter les deux postes · P3 + P4

- [ ] **2.1** Point d'accès mobile Windows `RESILIENCE-G2`, Hôte en `192.168.137.1`
- [ ] **2.2** `LAB_BIND=192.168.137.1` dans `.env`, puis `docker compose up -d --force-recreate waf`
- [ ] **2.3** Règle pare-feu Windows pour le port 8080, limitée au sous-réseau du groupe
- [ ] **2.4** PC Attaquant : connecté **uniquement** au PA, Python 3.12 + `httpx`, copier **seulement**
      `scripts/attack_lab.py` (jamais les secrets)
- [ ] **2.5** Vérifier depuis l'Attaquant que `http://192.168.137.1:8080` répond

## Phase 3 — Les deux jalons critiques · toute l'équipe

- [ ] **3.1** 🔴 **Jalon M7** — 1ʳᵉ attaque réelle
      Hôte : `python scripts/check_mardi.py --last 120` après l'attaque
      Attaquant : `python attack_lab.py --lab-authorized --seconds 30`
      *Fait quand* : 5/5 OK — pic **mesuré** dans Prometheus **et** `anomaly=true` sur la même fenêtre.
- [ ] **3.2** 🔴 **Jalon W7** — la boucle complète sous 60 s
      Hôte : `python scripts/acceptance.py --url http://192.168.137.1:8080 --seconds 55`, puis attaque,
      puis `python scripts/check_mercredi.py`
      *Fait quand* : 5/5 OK — boucle complète, < 60 s, aucune intervention humaine, config du détecteur consignée.
- [ ] **3.3** Si faux positifs ou détection trop lente : calibrer
      `python scripts/calibrate_detector.py --baseline … --normal … --attack …` (procédure : `docs/05-ML-RAG.md`)
      **L'outil propose, l'équipe décide.** Appliquer le couple retenu dans `.env`.
- [ ] **3.4** Décider d'activer ou non le **ban d'IP** (surcouche optionnelle)
      `docker compose -f compose.yaml -f compose.ban.yaml up -d` + la checklist de `docs/06-SECURITE.md`, décision 1.
      Si un seul des 4 points échoue : **ne pas l'activer**, rien d'autre n'en dépend.

## Phase 4 — Les trois trous de code restants · P1 + P2

- [ ] **4.1** `run-demo.sh` — **absent**, et indispensable pour réinitialiser entre deux prises du clip
      *Fait quand* : une seule commande remet l'environnement à l'état initial, de façon fiable.
- [ ] **4.2** Panneau **état des composants** sur le dashboard
      Le sujet l'exige explicitement (§3.1 : « observer les **composants**, les événements, les alertes et
      l'avancement »). Aujourd'hui on montre le chrono, les incidents, l'état ML et le SOC — pas la santé des services.
- [ ] **4.3** Deux défauts d'affichage du front : le bandeau d'erreur n'est jamais effacé après une reprise,
      et une réponse non JSON (502/504/403 du WAF) affiche une erreur d'analyse au lieu du statut.

## Phase 5 — Recette et clip (jeudi matin) · toute l'équipe

- [ ] **5.1** 5 exécutions consécutives réussies **sous 45 s** · `python scripts/check_mercredi.py --max-seconds 45`
- [ ] **5.2** Tester `run-demo.sh` entre deux essais
- [ ] **5.3** Mesurer RTO/RPO réels et les consigner (champ `user_visible_outage` de la preuve)
- [ ] **5.4** Tester la restauration de la base · `backup.py` puis `restore.py` (hors live)
- [ ] **5.5** Tourner le **Clip Chrono** : 60 s max, plan séquence, **3 prises de secours**
- [ ] **5.6** Répétition complète du live : enchaînement, répartition de la parole, passage aux clips de secours

## Phase 6 — Livrables (gel 17h00, remise 23h59) · P6 + tous

- [ ] **6.1** `Workshop2026-M2-G2-Dossier.pdf` (8–12 p.) — plan dans `docs/09-RECETTE-RENDU.md`
      ⚠️ Doit contenir les **chiffres réels** (RTO/RPO mesurés, faux positifs, temps de reprise) et
      **rendre visible la contribution de chacun** (exigé §7.1, aujourd'hui absent du dépôt).
- [ ] **6.2** `Workshop2026-M2-G2-Pres.pptx`
- [ ] **6.3** `Workshop2026-M2-G2-VidChrono.mp4`
- [ ] **6.4** `Workshop2026-M2-G2-Code.zip` · `python scripts/package.py` ✅ *script prêt et vérifié*
- [ ] **6.5** Les 4 fichiers dans le dossier `Workshop2026-M2-G2/`, noms exacts contrôlés
- [ ] **6.6** 🔴 **GEL DU CODE 17h00** — plus aucune modification ensuite
- [ ] **6.7** Remise avant 23h59

## Phase 7 — Vendredi (aucune production)

- [ ] **7.1** Se connecter au dashboard **avant** la démo (un flot de connexions peut verrouiller le login opérateur)
- [ ] **7.2** Clips de secours lisibles sur le poste de présentation
- [ ] **7.3** Démo live — **personne ne touche au clavier pendant la reprise**

---

## À faire en parallèle, sans dépendance

- [ ] Corriger le tableau Trello : G6 → G2 (4 cartes : L4, J5, J8, J9) et refléter l'état réel
- [ ] Relecture de `docs/06`, `07`, `08` par P6 — notamment valider la **décision 3** (jeton HMAC), que j'ai
      rédigée à partir du code sans validation d'équipe
- [ ] Faire passer la suite complète **sous Linux/WSL** : `python -m pytest -q`
      *(1 test échoue aujourd'hui sous Windows : `test_native_chain`, Ansible n'y tourne pas — ce n'est pas un bug du code)*
- [ ] Préparer les réponses aux questions du jury (antisèche : section « Dette assumée » de `ETAT-SEMAINE.md`)

## Preuves à conserver pour le dossier

À chaque exécution réussie, garder le fichier : `runtime/evidence/acceptance-*.json` (étapes horodatées,
temps détection → reprise, verdict de la transaction témoin, config du détecteur, version du code) et
`runtime/evidence/m7-proof-*.json`. **Ne citer dans le dossier que les preuves marquées `complete: true`.**

## Déjà acquis (pour mémoire, rien à faire)

Les 5 contrats d'API vérifiés contre le code · chaîne de remédiation codée et testée (26 tests sur le ban,
6 sur la transaction témoin) · chrono du dashboard sur horodatages réels · SIEM corrélé par incident ·
secrets SOPS vérifiés · RAG avec 503 explicite · EBIOS / PCA-PRA / NIS2-DORA rédigés · scripts de preuve
(`check_lundi`, `check_mardi`, `check_mercredi`, `acceptance`, `calibrate_detector`) · archive de rendu.
