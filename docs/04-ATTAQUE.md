# Scénario d'attaque — saturation de capacité par devis

> **Périmètre.** Cette attaque ne s'exécute que sur le réseau de laboratoire isolé
> `RESILIENCE-G2` (`192.168.137.0/24`), contre le SI fictif du groupe. Jamais sur le
> réseau du campus, un autre groupe, un équipement tiers ou Internet (sujet, §9).
> En cas de doute sur le périmètre : arrêter et prévenir le coach.

Statut : scénario **à valider par l'équipe et le coach** (carte L4). Le comportement
décrit ci-dessous est celui du code ; les mesures sur le matériel réel restent à
consigner (checklist de recette deux PC, `docs/09-RECETTE-RENDU.md`).

## Réseau et cible

| Élément | Valeur |
|---|---|
| Point d'accès | Point d'accès mobile Windows `RESILIENCE-G2` |
| Sous-réseau | `192.168.137.0/24` |
| PC Hôte (cible) | `192.168.137.1`, port `8080` : le WAF, seul point d'entrée publié |
| PC Attaquant | connecté uniquement à ce point d'accès, sans connexion parallèle au campus |
| Services non publiés | base, secrets, remédiateur, Ollama : aucun port exposé au réseau du groupe |

La cible est `http://192.168.137.1:8080` par défaut. Elle se change avec `--target`
ou la variable d'environnement `LAB_TARGET` (la ligne de commande l'emporte), mais
uniquement vers une **IP littérale** du sous-réseau ci-dessus ou de loopback. Un nom
d'hôte, une adresse du campus ou une adresse Internet est refusé avant toute connexion
(`scripts/attack_lab.py`, fonction `resolve_target`, couverte par `tests/test_configs.py`).

## Scénario retenu

**Abus d'une fonction légitime pour saturer une capacité partagée** : un client
authentifié à faible privilège (`loadbot`) enchaîne des demandes de devis valides.

- Le devis occupe 0,6 s un emplacement de capacité aval simulée ; le paiement en occupe
  un 0,08 s. Il n'y a que **4 emplacements, partagés** entre devis et paiements. C'est
  un défaut de conception volontaire du laboratoire (`services/payment/main.py`).
- À 20 requêtes/s, les devis demandent en moyenne ~12 emplacements pour 4 disponibles :
  la capacité reste saturée et les **paiements de l'opérateur reçoivent `503`**
  (`Simulated downstream capacity exhausted`), sans aucune ligne de débit.
- Les requêtes sont **valides** : le WAF (ModSecurity/CRS) ne les bloque pas. La
  détection repose donc sur le comportement (ML sur métriques et journaux), pas sur une
  signature (`docs/06-SECURITE.md`).
- Ce que le scénario n'est pas : ni compromission, ni fuite de données, ni élévation de
  privilèges. La reprise démontrée est un **retour de disponibilité** ; elle ne corrige
  pas une compromission (`docs/02-ARCHITECTURE.md`).

Réponse automatique attendue : détecteur ML, alerte signée, playbook
`infra/ansible/contain.yml`, qui active l'admission d'**un devis par identité et par
seconde**, puis le remédiateur rejoue une transaction et contrôle le total du registre
(200 000 centimes). Le flux d'attaque continue : les paiements repassent en `200` et le
`loadbot` reçoit des `429` (« 429 après confinement est attendu »).

## Bornes exactes

| Borne | Valeur | Où elle est appliquée |
|---|---|---|
| Débit | 20 requêtes/s maximum (une nouvelle requête toutes les 50 ms) | boucle d'envoi |
| Concurrence | 12 requêtes en vol, 12 connexions maximum | boucle d'envoi, `httpx.Limits` |
| Volume total | 700 requêtes maximum | boucle d'envoi |
| Durée | `--seconds` de 5 à 35, **30 par défaut** (~600 requêtes à 30 s) | contrôle des arguments |
| Délai par requête | 2 s | client HTTP |
| Cible unique | `POST /api/quotes` avec `{"amount_cents": 100}`, après un login `loadbot` | code du script |
| Périmètre | IP littérale de `192.168.137.0/24` ou loopback, port fixé à 8080 | `resolve_target` |
| Accord explicite | `--lab-authorized` **obligatoire**, sinon le script refuse de démarrer | contrôle des arguments |

Aucun scan, aucun exploit, aucune redirection suivie, aucun accès hors du WAF.

## Lancement

Préparation du PC Attaquant : voir `docs/INSTALL.md` §7 (copier uniquement
`scripts/attack_lab.py`, Python 3.11/3.12, `httpx==0.28.1`).

1. Sur le **PC Hôte**, lancer l'observateur, qui vérifie une transaction initiale puis
   attend l'attaque :
   ```bash
   python scripts/acceptance.py --url http://192.168.137.1:8080 --seconds 55
   ```
2. Au message « Start attack_lab.py on the ATTACKER PC now », sur le **PC Attaquant** :
   ```powershell
   .\.venv\Scripts\python attack_lab.py --lab-authorized --seconds 30
   ```
   Autre cible du lab : `--target 192.168.137.20` ou `$env:LAB_TARGET = "192.168.137.20"`.
3. Saisir le mot de passe du compte fictif `loadbot` à l'invite. Il est transmis
   localement par le groupe, jamais en argument de ligne de commande, jamais dans le
   dépôt ni dans une capture.
4. Observer sur l'Hôte : dashboard, Grafana, puis `runtime/evidence/acceptance-*.json`.

## Ce qu'on doit observer (à consigner dans la recette, `docs/09-RECETTE-RENDU.md`)

- Avant : une transaction fictive réussit (`200`).
- Pendant : des `503` sur `/api/payments`, `lab_capacity_denied_total` et
  `lab_active_work` qui montent, journaux `capacity_denied` dans Loki.
- Détection : `/ops/ml` passe à `monitoring` avec un score négatif ; une alerte est livrée.
- Après : incident `recovered`, nouvelle transaction `200`, total du registre à 200 000.

Le test d'intégration natif (`tests/test_native_chain.py`) reproduit ce 503 avec huit
clients simulés ; il ne remplace pas la mesure sur le matériel réel.
