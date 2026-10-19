# Correctifs MARDI — Project Resilience Alpha

Prompt à donner à l'agent VS Code, à la racine du dépôt :

> Lis `FIX-MARDI.md` et exécute les tâches dans l'ordre.

**Périmètre : la tâche 0 (clôture de lundi) puis les cartes MARDI (M1 → M7)**
du tableau Trello (`trello-snapshot.json`). Rien de mercredi, jeudi ou vendredi.
Tout problème hors périmètre se note dans le rapport final, ne se corrige pas.

**Objectif de la journée, en une phrase :** rendre le jalon critique M7
atteignable — l'attaque produit un pic visible **et** le modèle renvoie
`anomaly=true`, sans se déclencher tout seul le reste du temps.

---

## 0. Garde-fous

Ces règles priment sur toutes les tâches ci-dessous.

1. **Tu ne réécris jamais l'historique git.** Pas de `rebase -i`, pas de
   `filter-branch`, pas de `force-push`.
2. **Tu ne génères et ne commites aucun secret.** `scripts/init_secrets.py`
   reste une action humaine.
3. **Tu ne lances pas l'attaque DoS** (`attack_lab.py`), tu ne démarres pas la
   stack, tu n'entraînes pas le modèle. Tu peux exécuter la suite de tests et
   instancier des applications en mémoire (`TestClient`) — tu l'as fait lundi,
   c'est acceptable, continue à le signaler dans le rapport.
4. **Avant toute suppression**, tu cherches les références et tu listes ce que
   tu comptes supprimer dans ta réponse, avant de le faire.
5. **Quand le code et le plan divergent et que le code est meilleur, on aligne
   le plan.** Deux exceptions explicites cette fois, en tâches 3 et 4.
6. Un commit par tâche, message en français, préfixé `fix(mardi):`,
   `feat(mardi):` ou `docs(mardi):`.

---

## 1. Clôturer lundi : remettre le dépôt d'aplomb — **avant tout le reste**

**Constat (décision 1 de ton rapport de lundi) :** git suit encore
`Workshop2026-M2-GX/...` alors que le working tree a les mêmes fichiers à la
racine. `HEAD` contient deux versions de certains fichiers (`docs/INSTALL.md`),
et la plupart des fichiers racine ne sont pas suivis.

**Décision prise par l'équipe : le projet vit à la racine du dépôt.**
Le ZIP de livraison sera construit séparément jeudi, il ne dicte pas la
disposition du dépôt.

**À faire :**
- Retirer de l'index tous les chemins `Workshop2026-M2-GX/` :
  `git rm -r --cached Workshop2026-M2-GX` (le `--cached` est obligatoire, on ne
  touche pas aux fichiers sur disque). Si le dossier existe encore physiquement
  **et** qu'il est un doublon strict de la racine, appliquer le garde-fou n°4
  puis le supprimer.
- Ajouter tous les fichiers racine légitimes. **Avant le `git add`**, vérifier
  ce qui va partir : `git add -An .` et relire la liste. Aucun `.secrets/`,
  `.env`, `*.key`, `*.pem`, `__pycache__`, `node_modules`, `*.joblib` ne doit
  apparaître. Si c'est le cas, c'est le `.gitignore` qu'on complète d'abord.
- Vérifier qu'il ne reste **aucun doublon** dans `HEAD` :
  `git ls-files | sed 's#^Workshop2026-M2-GX/##' | sort | uniq -d` doit être vide.
- Vérifier que le dépôt est cohérent : `git status --short` propre après commit,
  et `git ls-files | wc -l` cohérent avec le nombre de fichiers du projet.

**Fini quand :** un `git clone` dans un dossier vierge donne exactement le
projet qui tourne, sans fichier manquant ni fichier en double.

---

## 2. Purger `.env.example`

**Constat (décision 2 de ton rapport) :** il contient `JWT_SECRET`,
`POSTGRES_PASSWORD`, `ORCHESTRATOR_TOKEN`. Les trois contredisent la conception
actuelle : les secrets vivent dans `.secrets/`, et il n'y a ni JWT ni
orchestrateur. C'est précisément le fichier qu'un correcteur ouvre pour se faire
une idée du projet.

**À faire :** le réduire à la configuration non secrète réellement lue par le
code (`LAB_BIND`, `OLLAMA_URL`, et ce que tu trouveras d'équivalent). Une ligne
de commentaire en tête doit dire que les secrets ne passent jamais par `.env`
mais par `.secrets/` via SOPS.

**Fini quand :** chaque variable de `.env.example` est effectivement lue
quelque part dans le code, et aucune n'est un secret.

---

## 3. Carte M5 — l'endpoint `/anomaly`

**Décision prise par l'équipe : on ajoute `/anomaly`.** C'est une des deux
exceptions au garde-fou n°5, et elle est assumée : l'endpoint a une vraie valeur
de démonstration devant le jury.

**À faire :**
- Ajouter au détecteur une route **en lecture seule** `GET /anomaly` qui renvoie
  au minimum `{"anomaly": bool, "score": float, "status": str}`.
- **Elle ne duplique aucune logique** : elle lit exactement le même état que
  `/ops/ml`. Si tu te retrouves à recopier le calcul du verdict, tu t'es trompé :
  extrais l'état dans une fonction unique que les deux routes appellent.
- `status` doit rester honnête : `waiting_for_trained_model` tant qu'aucun
  modèle n'est chargé, et dans ce cas `anomaly` vaut `false` **et** le champ
  `status` le dit. On ne renvoie jamais un `false` qui ferait croire à une
  absence d'anomalie alors qu'on ne mesure rien.
- Documenter la route dans la spec OpenAPI du détecteur, au même niveau de
  rigueur que ce que tu as fait lundi pour les quatre autres.
- `/ops/ml` reste en place, inchangé.

**Fini quand :** `/anomaly` existe, est documenté, et un test montre qu'il
renvoie le même verdict que `/ops/ml` dans les trois états (pas de modèle,
trafic normal, anomalie).

---

## 4. Carte M5 — la calibration du seuil, le vrai travail de la journée

**Constat (décision 6 de ton rapport) :** sur ta fixture synthétique, 3 points
normaux sur 18 franchissent la frontière avec `nu=0.03`, soit environ 17 % de
faux positifs. Si ce taux se confirme sur la vraie baseline, le détecteur se
déclenche tout seul pendant la démonstration et déclenche une remédiation sans
attaque. C'est le risque n°1 de la semaine après l'autonomie de la chaîne.

**À faire côté code, maintenant :**
- Rendre `nu` et la règle `consecutive >= 3` **configurables** (variables
  d'environnement ou fichier de configuration), pas des constantes dans le code.
  Sans ça, calibrer veut dire rebuild de l'image à chaque essai, et on y passera
  la soirée.
- Écrire `scripts/calibrate_detector.py` : il charge un jeu de baseline et un
  modèle existants, balaie une grille de `nu` et de `consecutive`, et sort pour
  chaque combinaison **le taux de faux positifs sur le trafic normal** et **le
  délai de détection** sur une fenêtre d'anomalie fournie. Sortie lisible en
  tableau **et** sérialisée en JSON dans `runtime/evidence/`.
- Le script **ne réentraîne pas** et **ne modifie pas** la configuration en
  place : il mesure et propose. Le choix final est humain.
- Documenter dans `docs/05-ML-RAG.md` la cible chiffrée à atteindre :
  **zéro faux positif sur une fenêtre de trafic normal soutenu**, et détection
  en moins de 10 secondes après le début de l'attaque. Si ces deux objectifs
  s'avèrent incompatibles sur la vraie baseline, c'est un arbitrage d'équipe —
  tu le signales, tu ne tranches pas.

**Tu ne lances ni la collecte ni l'entraînement ni la calibration** (garde-fou
n°3). Tu livres l'outil et la cible, un humain mesure.

**Fini quand :** quelqu'un peut, en une commande, obtenir un tableau qui dit
quel couple (`nu`, `consecutive`) donne zéro faux positif avec la détection la
plus rapide.

---

## 5. Carte M1 — le budget de connexion de `/auth/token`

**Constat (décision 4 de ton rapport) :** 30 tentatives par minute et par
adresse vue par le service. Derrière le WAF, aucun `X-Forwarded-For` n'est
approuvé, donc cette adresse est celle du proxy : **le budget est partagé par
tous les clients**, y compris la connexion que fait le remédiateur pour vérifier
la reprise. Pendant un DoS, l'attaquant peut épuiser ce budget et faire échouer
la vérification métier — qui tombe alors en `manual_review_required`.

Traduit en termes de notation : **l'attaque pourrait provoquer exactement le
scénario qui vaut 0/5 vendredi**, sans que personne ne touche au clavier.

**À faire :**
- Vérifier dans le code si le diagnostic tient (tu l'avais déduit de la
  configuration, pas observé). S'il ne tient pas, le dire et passer à la suite.
- S'il tient, corriger de la façon la moins invasive : exempter du budget la
  voie interne qu'emprunte le remédiateur — identité de service dédiée, chemin
  réseau interne non exposé, ou budget séparé. **Ne supprime pas le rate-limit**,
  il protège une vraie surface.
- Ajouter un test qui prouve que la vérification métier du remédiateur aboutit
  alors même que le budget public est épuisé.
- Documenter le choix dans `docs/06-SECURITE.md`.

**Fini quand :** un test échoue si quelqu'un réintroduit le couplage entre le
budget public et la voie du remédiateur.

---

## 6. Cartes M2, M3, M4 — vérifier, ne pas réécrire

L'audit les donne complètes. Ton travail ici est de confirmer, pas de refaire.

- **M2 (front)** : plus aucune référence à un mock actif dans le chemin de
  paiement, l'appel va bien sur `/payments`, et la branche d'erreur affiche
  quelque chose d'utile quand l'API renvoie 503 (c'est l'état qu'aura le service
  pendant une remédiation — le jury le verra).
- **M3 (Ansible + métriques)** : chaque playbook de `infra/ansible/` est
  syntaxiquement valide (`ansible-playbook --syntax-check`) et exécutable seul.
  Les séries applicatives sont bien déclarées côté Prometheus.
- **M4 (attaque)** : le script est déterministe à paramètres égaux. Le critère
  de la carte est « deux lancements successifs produisent le même effet » — ce
  qui se prouve en exécution, mais tu peux déjà vérifier qu'aucune part
  d'aléatoire non graînée ne rend l'attaque irreproductible.

Pour chacune : `CONFIRMÉ` ou `ÉCART` avec fichier et ligne. Pas de réécriture.

---

## 7. Carte M6 — auditer les documents de gouvernance

**Constat :** `docs/06-SECURITE.md`, `07-GOUVERNANCE.md` et `08-PCA-PRA.md`
existent mais n'ont jamais été relus contre le code. C'est le même piège que les
contrats d'API lundi : un document qui décrit un système imaginaire est pire que
pas de document, parce qu'on le livre au jury.

**À faire :** relire les trois en cherchant **uniquement** les affirmations
factuelles sur le système, et vérifier chacune contre le code. En particulier,
tout passage qui parlerait de recréation de conteneur, de bannissement d'IP, de
JWT, d'IsolationForest, d'orchestrateur ou de `/pay` est faux aujourd'hui.

Tu corriges les affirmations factuellement fausses. Tu **ne touches pas** au
contenu de gouvernance lui-même (analyse de risques, procédures, RTO/RPO
annoncés) : ce n'est pas ton rôle, et P6 en répond. Tu listes ce que tu as
changé et ce que tu as laissé.

**Fini quand :** aucune phrase des trois documents ne décrit un composant qui
n'existe pas.

---

## 8. Carte M7 — préparer la preuve du jalon critique

Le jalon est runtime, mais il mérite mieux qu'une capture d'écran prise à la
volée pendant que tout le monde regarde.

**À faire :** créer `scripts/check_mardi.py`, sur le modèle de `check_lundi.py`,
qui **constate sans rien démarrer** et sort en code 0 ou 1 :
1. un modèle entraîné est chargé — `/anomaly` ne renvoie plus
   `waiting_for_trained_model` ;
2. au repos, `/anomaly` renvoie `anomaly=false` ;
3. les séries d'attaque sont bien présentes dans Prometheus sur la fenêtre
   demandée (le « pic visible dans Grafana » du plan, mesuré au lieu d'être
   regardé) ;
4. sur cette même fenêtre, le détecteur a bien produit `anomaly=true` ;
5. il sérialise la preuve dans `runtime/evidence/` avec horodatage.

Le script prend la fenêtre temporelle en paramètre : on lance l'attaque à la
main, puis on lui demande de vérifier ce qui s'est passé entre telle et telle
heure. Chaque étape affiche `OK` ou `ECHEC` avec la raison.

**Fini quand :** le jalon M7 peut être prouvé par une commande et un fichier de
preuve, pas par un témoignage.

---

## 9. Hors périmètre — à signaler, pas à corriger

- `tests/test_ml_rag.py::test_document_retrieval_is_grounded` échoue sous
  Windows (encodage cp1252 vs UTF-8). Carte W5, mercredi.
- Les constantes de périmètre dupliquées entre `attack_lab.py` et
  `lab_client.py` : ta justification de lundi tient, on ne fusionne pas.
- La suite de tests complète (`test_api`, `test_alerts`, `test_ledger`,
  `test_native_chain`) n'a jamais été passée en entier. Rappelle-le dans le
  rapport : c'est une action humaine sous WSL.

---

## 10. Rapport de sortie

Termine par `RAPPORT-FIX-MARDI.md`, même structure que lundi :
**Fait** (tableau avec commits et fichiers) · **Non fait et pourquoi** ·
**Décisions qui ne m'appartiennent pas** · **Incidents** ·
**Reste à faire par un humain**.

Ajoute une section **« Prêt pour M7 ? »** : la liste des conditions du jalon
critique, et pour chacune si elle est satisfaite, en attente d'exécution, ou
bloquée.

Puis, en trois lignes maximum dans ta réponse : ce qui est débloqué, ce qui
reste bloquant pour M7, et ce qu'un humain doit lancer maintenant.
