# Validation effective — 19 octobre 2026

Cette page distingue les résultats observés dans l'environnement de construction
Linux des essais qui doivent encore être réalisés sur Windows et deux PC.

| Élément | Résultat réellement obtenu | Limite de la preuve |
|---|---|---|
| Suite pytest | **24 tests réussis**, un avertissement de dépréciation Starlette/AnyIO, 15,50 s | SQLite et fixtures ; voir evidence/pytest.xml et pytest.txt |
| Registre et idempotence | Transfert, conservation, concurrence 40 appels / même clé, fonds insuffisants testés | PostgreSQL non lancé ici |
| API et accès | Rôles, sessions forgées/expirées, montants invalides et contrôle interne testés | Aucun test d'intrusion exhaustif |
| Saturation puis admission | Paiement 503 avant protection, paiement 200 pendant charge après protection | Capacité aval volontairement simulée |
| Alerte | Signature, déduplication, fraîcheur et nombres invalides testés | Horloges et réseau deux PC à vérifier |
| Chaîne native HTTP | Serveurs auth/payment/remediator/proxy réellement lancés ; score ML ; alerte HMAC ; **véritable Ansible** ; paiement vérifié pendant charge encore active | SQLite, proxy de test à la place du WAF ; apprentissage sur fixture synthétique ; collecteur de production non lancé |
| Échec de vérification métier | L'état reste failed si la transaction ne peut être vérifiée | Cas unitaire avec injection d'échec |
| Modèle ML | Apprentissage/scoring exécutés sur fixture de test, refus baseline polluée et données non finies | Pas de baseline réelle du laboratoire ni métrique d'efficacité réelle |
| Recherche documentaire | Tests de récupération de sources réussis | Génération LLM non exécutée |
| Imports RAG | LangChain/Ollama et corpus chargés avec les versions retenues ; schémas OpenAPI générés | Aucun serveur Ollama, aucun modèle téléchargé ici |
| Frontend | **Build Vite/React/Tailwind réussi**, 23 modules, 5,54 s | Interface non vérifiée visuellement ni dans un navigateur Windows |
| Ansible déploiement | Syntax-check réussi ; playbook de correction réellement exécuté au test natif | Déploiement Compose lui-même non exécuté |
| Configurations | YAML Compose et playbook parsés, tests d'exposition et d'absence de socket réussis | Pas d'exécution docker compose config ni validation des binaires tiers |
| Docker / WSL2 / PostgreSQL | **Non exécutés ici : Docker absent** | À installer/tester sur Hôte Windows |
| WAF / Prometheus / Grafana / Loki / Alloy / SOC | Code et configurations fournis | Collecte, filtres CRS et corrélation réels à vérifier en Compose |
| SOPS / age | Scripts fournis, secrets exclus de l'archive | Cycle chiffrer/déchiffrer non exécuté ici |
| Backup / restauration | Scripts et contrôle SHA256 fournis | pg_dump/pg_restore Docker non exécutés |
| PDF / PowerPoint / Clip Chrono | Plans et storyboard fournis | Fichiers finaux et capture réelle à produire après recette |

## Versions Python vérifiées
Python 3.12, FastAPI 0.115.12, HTTPX 0.28.1, scikit-learn 1.6.1, NumPy 2.2.5,
Ansible Core 2.18.4, LangChain Core 0.3.59, langchain-ollama 0.3.2, client Ollama 0.6.3.
Les versions des images Docker sont des références de configuration, pas des
versions démarrées et vérifiées ici. Certains tags restent mobiles ; figer les
digests après pull et contrôler les vulnérabilités avant une utilisation durable.

## Ce qui n'est pas affirmé
Aucune démonstration complète sur deux PC, aucun RTO mesuré sur le Hôte,
aucune performance réelle de détection, aucune conformité NIS2/DORA,
aucune génération Ollama ou restauration PostgreSQL réussie n'est annoncée.
Le code et les procédures permettent de mener ces validations et d'enregistrer
leurs résultats, y compris un échec.

## Recette suivante
Suivre docs/INSTALL.md puis docs/09-RECETTE-RENDU.md. Ajouter les preuves réelles
de Windows, des conteneurs, du second PC, du modèle nominal entraîné et du
paiement après incident. Réviser cette page uniquement à partir des observations.
