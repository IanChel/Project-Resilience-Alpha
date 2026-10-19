# Contrats d'interface

JSON UTF-8. Montants en centimes entiers. `Authorization: Bearer <session>`
obtenu via l'authentification ; session d'une heure, conservée seulement en mémoire
par le navigateur. Les exemples de jetons sont des emplacements, pas des secrets.

| Appel | Émetteur → destinataire | Entrée | Sortie / erreurs | Publication |
|---|---|---|---|---|
| POST /auth/token | navigateur/client → auth via WAF | username, password | access_token ; 401, 429 | PA |
| POST /api/payments | opérateur → payment via WAF | amount_cents, recipient=merchant ; Idempotency-Key | transaction{id,idem,amount,recipient,created}, replayed ; 401/403/409/422/503 | PA |
| POST /api/quotes | opérateur ou loadbot → payment | amount_cents | devis ; 429 admission, 503 capacité | PA |
| GET /api/accounts | opérateur → payment | Bearer opérateur | accounts, dernières transactions, total_cents | PA |
| GET /api/ready | observateur → payment | aucune | DB accessible ; pas une preuve métier | PA |
| GET /ops/status | opérateur → remediator | Bearer opérateur | incidents, état, preuves | PA lecture seule |
| GET /ops/ml | opérateur → detector, contrôle auth_request | Bearer opérateur | état modèle, score, features, signaux SOC | PA lecture seule |
| GET /anomaly | outil de recette → detector | aucune, réseau interne | anomaly (bool), score (null si non mesuré), status | Interne |
| POST /rag/ask | opérateur → rag | question 3–1000 caractères | answer, sources ; 429/503 | PA |
| GET /metrics | Prometheus → payment | aucune, réseau interne | exposition Prometheus | Interne |
| POST /alerts | detector → remediator | UUID id, issued_at, score négatif, 4 features, `sources` optionnel (adresses vues par le WAF) | 202 accepté/dédupliqué ; 403/413/422 | Interne |
| POST /control/contain | Ansible → payment | X-Control-Key ; action fixe | contained=true, changed bool | Interne |

## Authentification des alertes
Header `X-Signature = hex(HMAC-SHA256(alert_key, octets JSON exacts))`.
L'émetteur signe les octets réellement envoyés. Fenêtre temporelle ±30 secondes,
UUID d'incident et déduplication persistante. Horloges synchronisées nécessaires.
Une alerte ne contient ni commande, ni nom de conteneur, ni URL de cible ; elle peut porter des
adresses sources (optionnelles), filtrées par le moteur avant tout ban.
Le moteur refuse un score non fini/positif, un vecteur invalide ou sans pression.

## Erreurs et reprise
Un 503 de paiement avant validation ne crée pas de débit. Réessayer une demande
incertaine avec la même clé et le même contenu pour éviter le double paiement.
L'interface simple crée une clé par clic ; une interface industrielle conserverait
la clé d'une demande incertaine jusqu'à résolution. Les tests couvrent le contrat
serveur d'idempotence et les accès concurrents.
Le moteur conserve sa propre clé `recovery-<incident>` entre les essais.

## Documentation OpenAPI
Les cinq contrats sont dans `docs/openapi/` (auth, detector, payment, rag, remediator). Ils
sont **maintenus à la main** : l'export brut de FastAPI ne décrit ni les réponses,
ni les codes d'erreur, ni le jeton (HMAC maison, pas un JWT), ni le corps de
`POST /alerts`. Chaque route y indique `x-exposure` (publiée par le WAF ou interne).
Le détecteur publie `/health` sous `/ops/ml` (état brut) et `/anomaly` (verdict de
l'observation courante, non publié) ; ils lisent le même état.

Pour contrôler qu'un contrat n'a pas dérivé du code, exporter le schéma brut dans un
autre dossier et comparer chemins, méthodes et champs de requête. Ne jamais écraser
`docs/openapi/` avec cet export :
`docker compose exec -T payment python -c "import json; from services.payment.main import app; print(json.dumps(app.openapi(),indent=2))" > runtime/payment-openapi.json`
Adapter pour auth et remediator ; l'import de rag construit son corpus (`DOCS_DIR`) et
exige LangChain, donc à exécuter dans son conteneur. Le code contient
aussi des routes internes : ne pas publier ces schémas comme contrat d'accès extérieur.
