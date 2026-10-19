# Correctifs MERCREDI — Project Resilience Alpha

Prompt à donner à l'agent VS Code, à la racine du dépôt :

> Lis `FIX-MERCREDI.md` et exécute les tâches dans l'ordre.

**Périmètre : les cartes MERCREDI (W1 → W7)** du tableau Trello
(`trello-snapshot.json`), précédées d'une vérification de clôture de mardi et
suivies d'une régression complète. Rien de jeudi ni de vendredi.

**Objectif de la journée, en une phrase :** la boucle complète
`attaque → détection → remédiation → service OK` tourne **sans aucun humain**,
en **moins de 60 secondes**, et elle est **visible à l'écran**.

C'est la journée du point noté 5/5. Tout le reste passe après.

---

## 0. Garde-fous

Identiques aux deux briefs précédents, ils priment sur tout le reste.

1. **Jamais de réécriture d'historique git.** Pas de `rebase -i`, pas de
   `filter-branch`, pas de `force-push`.
2. **Tu ne génères et ne commites aucun secret.**
3. **Tu ne lances pas l'attaque DoS**, tu ne démarres pas la stack, tu
   n'entraînes pas le modèle. Tu peux exécuter la suite de tests et instancier
   des applications en mémoire (`TestClient`) — signale-le dans le rapport,
   comme les fois précédentes.
4. **Avant toute suppression**, tu cherches les références et tu listes ce que
   tu comptes supprimer dans ta réponse, avant de le faire.
5. **Quand le code et le plan divergent et que le code est meilleur, on aligne
   le plan.** Une exception assumée cette fois, en tâche 2.
6. Un commit par tâche, message en français, préfixé `fix(mercredi):`,
   `feat(mercredi):` ou `docs(mercredi):`.

---

## 1. Vérifier que mardi est réellement clos — **avant tout le reste**

Ne pars pas du principe que mardi est terminé. Relis `RAPPORT-FIX-MARDI.md` et
vérifie dans le dépôt, pas dans le rapport :

- le dépôt est à plat : `git status --short` est propre, et
  `git ls-files | sed 's#^Workshop2026-M2-GX/##' | sort | uniq -d` ne renvoie
  rien ;
- `GET /anomaly` existe et est documenté dans la spec du détecteur ;
- `nu` et la règle `consecutive` sont configurables sans rebuild d'image ;
- `scripts/calibrate_detector.py` et `scripts/check_mardi.py` existent ;
- `.env.example` ne contient plus aucun secret ;
- le budget de `/auth/token` ne starve plus la voie du remédiateur, et un test
  le prouve.

**Si l'un de ces points manque**, tu le traites **avant** d'entamer mercredi, et
tu le signales en tête du rapport. Construire la boucle autonome sur une
détection non calibrée ne sert à rien : elle se déclenchera toute seule.

---

## 2. Carte W1 — fermer le moteur de remédiation

**État (audit) :** 6 items sur 8 sont faits, la chaîne est déjà autonome sur le
chemin nominal. Manquent le **bannissement d'IP** et la **recréation de
conteneur**.

**Décision prise par l'équipe :**
- **On ajoute le bannissement d'IP.** Peu coûteux, très visible en démonstration,
  et il ferme un des deux trous.
- **On n'ajoute pas la recréation de conteneur.** C'est un choix de durcissement
  assumé : on ne confie pas le socket Docker au remédiateur. Il doit être
  **documenté et défendable**, pas subi.

### 2a. Bannissement d'IP

- Ajouter au playbook `infra/ansible/contain.yml` une tâche qui bannit la ou les
  adresses sources identifiées dans l'alerte, au niveau du WAF.
- **L'IP bannie vient de l'alerte signée**, jamais d'un en-tête de requête :
  un attaquant qui contrôle `X-Forwarded-For` pourrait sinon faire bannir une
  adresse de son choix — y compris celle du proxy, ce qui couperait tout le
  service. Si l'alerte ne porte pas aujourd'hui l'adresse source, c'est le
  détecteur qu'il faut compléter, pas le playbook qu'il faut bricoler.
- **Le ban doit expirer** (TTL) ou être explicitement levable. Un ban permanent
  posé par une détection à faux positif, c'est un déni de service qu'on
  s'inflige soi-même pendant la soutenance.
- **Ne jamais bannir** les adresses internes de la stack ni le réseau de
  l'observateur : une liste d'exclusion explicite, testée.
- Le playbook reste **idempotent** : rejoué sur une IP déjà bannie, il réussit
  sans erreur.
- Ajouter un test qui prouve les trois points : l'IP vient de l'alerte, les
  adresses internes ne sont jamais bannies, et le rejeu est idempotent.

### 2b. Documenter le choix de ne pas recréer le conteneur

Dans `docs/06-SECURITE.md`, une décision numérotée, trois paragraphes maximum :
ce qu'on fait à la place (contrôle d'admission applicatif + ban d'IP), pourquoi
(ne pas exposer le socket Docker à un service qui traite des entrées venues du
réseau), et ce que ça coûte (un conteneur compromis ne serait pas remplacé — on
contient, on ne reconstruit pas).

Écris-la pour qu'un membre du groupe puisse la lire à voix haute devant le jury
et répondre à « pourquoi vous ne redémarrez pas le conteneur ? ». C'est la
question qui tombera.

### 2c. Revalider les 8 items

Reprends la checklist W1 du Trello item par item et donne pour chacun
`FAIT` / `DIVERGENT ASSUMÉ` / `RUNTIME`, avec fichier et ligne. L'item 4
(recréation de conteneur) devient `DIVERGENT ASSUMÉ` avec renvoi à la décision
écrite en 2b.

---

## 3. Carte W2 — le chrono du dashboard

**État (audit) :** la timeline existe et se rafraîchit toutes les 2 secondes,
mais **il n'y a pas de chrono affiché** — or la carte l'exige, et c'est ce que
le jury regardera pendant toute la démonstration.

**À faire :**
- Afficher un chronomètre qui démarre à la **détection** et s'arrête au
  **service rétabli et transaction témoin validée**. C'est ce temps-là qui doit
  passer sous 60 secondes aujourd'hui et sous 45 jeudi.
- Le temps affiché doit venir des **horodatages réels** portés par les
  évènements (alerte, début de remédiation, healthcheck OK, transaction témoin),
  jamais d'un compteur lancé côté navigateur à l'ouverture de la page. Un chrono
  côté client qui ne mesure rien, c'est exactement ce qu'un correcteur attentif
  repère.
- Afficher les quatre étapes avec leur horodatage, pour qu'on voie où passe le
  temps quand c'est trop long.
- Gérer l'état « pas d'incident en cours » proprement : pas de chrono à zéro qui
  tourne dans le vide.

**Fini quand :** pendant un incident, l'écran montre le temps écoulé depuis la
détection et le détail des quatre étapes, à partir des données du backend.

---

## 4. Carte W3 — transaction témoin

**État (audit) :** `FAIT`, et bien faite — rejeu de paiement via le WAF plus
contrôle d'intégrité du registre.

**À faire :** confirmer, pas réécrire. Vérifier que le ban d'IP ajouté en tâche
2 **ne bloque pas** la transaction témoin : elle passe par le WAF, et si elle
part d'une adresse qui vient d'être bannie, la vérification métier échouera et
la chaîne tombera en `manual_review_required` — le scénario à 0/5.

C'est le point d'interaction le plus dangereux de la journée. Ajoute un test
qui prouve que la transaction témoin aboutit alors qu'un ban est actif.

---

## 5. Carte W4 — WAF, SIEM, secrets

**État (audit) :** `PARTIEL`. Le ban d'IP est traité en tâche 2. Reste à
vérifier le reste.

- **Rate-limit** : l'audit note qu'il est applicatif, pas au niveau du WAF.
  Vérifie si c'est encore le cas après la tâche 2 et documente l'état réel —
  on ne déplace rien aujourd'hui, on décrit juste ce qui existe.
- **SIEM** : les règles LogQL de `services/detector/soc.py` corrèlent-elles
  réellement les évènements d'un incident (alerte, remédiation, reprise), ou
  seulement des lignes isolées ? Si la corrélation est partielle, complète-la.
- **SOPS** : vérifie qu'aucun secret déchiffré n'est écrit ailleurs que dans
  `.secrets/runtime/`, et que ce chemin est bien ignoré par git.

---

## 6. Carte W5 — RAG, et le test qui échoue

**État (audit) :** `PARTIEL`. LangChain + Ollama en place, récupération TF-IDF
(pas Chroma), génération runtime.

**À faire :**
- **Corriger `tests/test_ml_rag.py::test_document_retrieval_is_grounded`.** Tu
  as identifié la cause lundi : le test écrit en cp1252 sous Windows, `Corpus`
  relit en UTF-8. Force l'encodage UTF-8 **des deux côtés**, écriture comme
  lecture. Ce n'est pas qu'un test : si le corpus est lu avec l'encodage par
  défaut de la plateforme, la doc française du projet sera mal indexée sur un
  poste Windows et le RAG répondra mal pendant la démonstration.
- **Documenter le choix TF-IDF** dans `docs/05-ML-RAG.md`, comme pour
  OneClassSVM : pourquoi TF-IDF suffit sur un corpus de cette taille, et ce
  qu'un index vectoriel apporterait. On ne change pas d'implémentation à deux
  jours du gel.
- Vérifier que le RAG indexe bien le `docs/` **actuel** — après les corrections
  de lundi et mardi, plus aucun document ne doit décrire un orchestrateur, un
  JWT ou une recréation de conteneur.
- Vérifier que l'absence de modèle Ollama tiré se traduit par un **503 explicite**
  et non par une réponse inventée.

---

## 7. Carte W6 — tests de restauration chronométrés

**État (audit) :** `RUNTIME`. Le harness `scripts/acceptance.py` existe.

**À faire :** t'assurer que la preuve produite est exploitable pour le dossier
PCA/PRA de P6 — c'est-à-dire qu'elle contient au minimum, par exécution : les
horodatages des quatre étapes, le temps total détection → service rétabli, le
verdict de la transaction témoin, et la configuration du détecteur utilisée
(`nu`, `consecutive`). Sans cette dernière, une mesure n'est pas reproductible.

Si un de ces champs manque, complète `acceptance.py`. Tu ne l'exécutes pas.

---

## 8. Carte W7 — préparer la preuve du chrono sous 60 s

Même principe que `check_lundi.py` et `check_mardi.py` : créer
`scripts/check_mercredi.py`, qui **constate sans rien démarrer** et sort en 0 ou 1.

Il lit la dernière preuve de `runtime/evidence/` et vérifie :
1. la boucle est allée jusqu'au bout — détection, remédiation, healthcheck,
   transaction témoin validée ;
2. le temps détection → service rétabli est **sous 60 secondes** ;
3. **aucune intervention humaine** n'apparaît dans la trace : pas de
   `manual_review_required`, pas de reprise manuelle ;
4. le ban d'IP a bien été posé **et** la transaction témoin a quand même abouti ;
5. la configuration du détecteur utilisée est consignée.

Chaque étape affiche `OK` ou `ECHEC` avec la raison. Pas de sortie muette.

---

## 9. Régression complète — l'état réel de lundi à mercredi

Dernière tâche de la journée, et la plus importante après W1.

**À faire :**

### 9a. Exécuter la suite de tests en entier

`python -m pytest -q`, **toute la suite**, pas une sélection. C'est la première
fois qu'elle tourne complètement depuis le début de la semaine — lundi tu n'avais
lancé que 4 fichiers sur 8. Pour `tests/test_native_chain.py`, qui démarre des
serveurs et Ansible : lance-le s'il passe dans ton environnement ; s'il exige la
stack, dis-le explicitement au lieu de le sauter en silence.

Reporte le résultat fichier par fichier, avec le détail de chaque échec.

### 9b. Rejouer les vérifications statiques des trois jours

Reprends les critères des trois briefs et dis, pour chacun, s'il tient
**encore** aujourd'hui. Les corrections de mercredi ont pu défaire celles de
lundi — c'est précisément ce qu'on cherche.

En particulier :
- aucun secret suivi par git (`git ls-files`), `.gitignore` toujours correct ;
- aucun fichier du scaffold mort réapparu ;
- les 5 specs OpenAPI (les 4 de lundi + `/anomaly`) décrivent toujours le code ;
- aucune référence à `/pay`, `docker-compose.yml`, JWT, IsolationForest ou
  orchestrateur dans le code **et dans la doc** ;
- `.env.example` toujours sans secret.

### 9c. Écrire le tableau de bord de la semaine

Produis `ETAT-SEMAINE.md`, une seule page, avec une ligne par carte de L1 à W7 :

```
| ID | Carte | Statut | Preuve | Bloquant pour |
```

Statuts : `FAIT`, `PARTIEL`, `RUNTIME`, `DIVERGENT ASSUMÉ`, `HORS-REPO`.
La colonne « Bloquant pour » dit ce qui est retenu en aval — c'est elle qui sert
à décider quoi faire jeudi matin.

Termine ce fichier par trois sections courtes :
- **Prêt pour le gel de jeudi 17h ?** oui/non et ce qui manque ;
- **Risques pour la note**, par gravité, avec en premier tout ce qui pourrait
  déclencher une intervention manuelle pendant le live ;
- **Dette assumée** : la liste des divergences documentées (OneClassSVM, jeton
  HMAC, pas de recréation de conteneur, TF-IDF), avec pour chacune le document
  où se trouve la justification. C'est la antisèche du groupe pour les
  questions du jury.

---

## 10. Rapport de sortie

Termine par `RAPPORT-FIX-MERCREDI.md`, même structure que les jours précédents :
**Fait** · **Non fait et pourquoi** · **Décisions qui ne m'appartiennent pas** ·
**Incidents** · **Reste à faire par un humain**.

Puis, en trois lignes maximum dans ta réponse : si la boucle autonome est
complète sur le papier, ce qui reste bloquant pour le jalon des 60 secondes, et
ce qu'un humain doit lancer maintenant.
