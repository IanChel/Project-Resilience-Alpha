# Installation — Windows / Docker Desktop / WSL2

Ces commandes sont à exécuter par l'équipe sur son PC. Elles n'ont pas été
exécutées ici dans Docker. Commencer en localhost, puis connecter les deux PC.
Le réseau est requis au téléchargement des paquets, images et modèle, pas pour
les réponses du RAG après installation.

## 1. Préparer Windows et WSL
Dans PowerShell administrateur si WSL n'est pas installé :
```powershell
wsl --install -d Ubuntu
wsl --update
wsl --list --verbose
```
Redémarrer si demandé. Installer Docker Desktop depuis son site officiel,
choisir le backend WSL2 et activer l'intégration Ubuntu. Démarrer Docker Desktop.
Le sujet exige les droits administrateur pour l'environnement du workshop ;
ne pas contourner une restriction d'un poste géré, demander au coach.

Dans le terminal Ubuntu WSL, placer le projet sous `~/resilience-alpha` plutôt
que sous `/mnt/c` pour les droits des secrets et les performances.
Décompresser l'archive et se placer dans son dossier contenant compose.yaml.
```bash
docker version
docker compose version
python3 --version
sudo apt-get update
sudo apt-get install -y python3-venv age
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```
Les commandes Python suivantes supposent ce venv actif. Python 3.11/3.12 convient
aux dépendances choisies ; les images exécutent Python 3.12.

## 2. Installer SOPS et générer les secrets
Installer le binaire Linux correspondant à l'architecture WSL depuis les releases
officielles https://github.com/getsops/sops/releases et vérifier le checksum publié.
Le nom de fichier dépend de la version : ne pas installer un binaire Windows dans WSL.
Après téléchargement, le renommer localement `sops`, puis :
```bash
sudo install -m 0755 ./sops /usr/local/bin/sops
sops --version
age-keygen --version
python scripts/init_secrets.py
```
Si `.secrets` existe déjà, ne pas régénérer au hasard. Restaurer les fichiers
runtime à partir du chiffré et de la clé : `python scripts/unseal.py`.
Pour vérifier un cycle SOPS sans afficher les valeurs :
```bash
SOPS_AGE_KEY_FILE="$PWD/.secrets/age.key" sops --decrypt .secrets/secrets.enc.json > /dev/null
```
La clé age privée, le JSON chiffré et les mounts runtime sont locaux et exclus
du ZIP. Lire docs/06-SECURITE.md pour les limites et la rotation.

## 3. Valider puis lancer les conteneurs
```bash
docker compose config --quiet
python -m pytest -q
python -m ansible.cli.playbook -i localhost, infra/ansible/deploy.yml
# Équivalent de lancement direct : docker compose up -d --build
docker compose ps
docker compose logs --tail=50 payment detector remediator alloy
```
Aucun secret ne doit être copié dans un rapport ou un échange avec une IA.
Les logs d'erreur tiers doivent être relus avant partage.
Tester http://127.0.0.1:8081/api/ready puis ouvrir http://127.0.0.1:8081.
(8081 = `LAB_PORT` : le port 8080 est occupé sur le PC Hôte par un service Java.)
Compte opérateur : alice. Son mot de passe est créé sur votre PC :
```bash
cat .secrets/runtime/alice_password
```
Cette commande affiche une valeur locale uniquement pour la saisir dans le
navigateur ; ne pas l'enregistrer dans la capture, un terminal partagé ou le dossier.
Grafana : http://127.0.0.1:3000, utilisateur admin ; mot de passe dans
`.secrets/runtime/grafana_password`. Le dashboard RESILIENCE est provisionné.

Vérifier le WAF séparément (docs/06-SECURITE.md). Les images et leur configuration
n'ont pas été testées ici : examiner les healthchecks et corriger tout échec de
démarrage avant la démonstration, sans désactiver les défenses.

## 4. Installer le modèle local du RAG
```bash
docker compose exec ollama ollama pull qwen2.5:1.5b
docker compose exec ollama ollama show qwen2.5:1.5b
```
Relever les paramètres et la version, puis poser une question dans le tableau
de bord. Le premier chargement CPU peut prendre du temps. En cas d'indisponibilité,
l'API RAG renvoie 503 plutôt qu'une réponse présentée comme réellement générée.

### Variante PC IA optionnel
Sur le troisième PC, installer uniquement Ollama, télécharger qwen2.5:1.5b et
l'exposer sur son IP du PA, port 11434. Restreindre ce port au seul PC Hôte dans
le pare-feu. L'API Ollama n'a pas d'authentification native dans cette configuration.
Sur Hôte, `.env` contient uniquement la configuration non secrète, par exemple
`OLLAMA_URL=http://192.168.137.3:11434` si cette IP a été réellement vérifiée.
Puis `docker compose up -d --force-recreate rag` et `docker compose stop ollama`.
Le frontal RAG, le corpus et LangChain restent sur le PC Hôte. Vérifier la route
Hôte→PC IA ; aucune ouverture vers le campus.

## 5. Collecter la baseline et entraîner le ML
Aucune attaque ni politique active pendant cette phase ; s'assurer que les
métriques ne contiennent plus de rejets de capacité récents. Premier terminal :
```bash
python scripts/normal_traffic.py --seconds 240
```
Saisir le mot de passe alice local. Dans un second terminal WSL, après environ
15 secondes de trafic et de collecte Prometheus/Alloy, collecter la baseline puis
entraîner (deux commandes, la seconde lit le fichier écrit par la première) :
```bash
docker compose exec detector python -m services.detector.collect_baseline
docker compose exec detector python -m services.detector.train
```
La collecte dure environ 3 minutes et écrit `/models/baseline.json` ; l'entraînement
est immédiat et écrit `/models/model.joblib` et `/models/report.json`. Relever le
rapport et attendre l'état `monitoring` dans le dashboard. Si une source manque ou la
baseline est polluée, la collecte échoue sans rien écrire : résoudre la cause avant
de retenter. Pas de fallback fictif. Si le code du détecteur a changé,
`docker compose up -d --build detector` d'abord. Détails : docs/05-ML-RAG.md.

Exporter les preuves ML sans exporter de secret :
```bash
mkdir -p runtime/evidence
docker compose cp detector:/models/report.json runtime/evidence/ml-report.json
docker compose cp detector:/models/baseline.json runtime/evidence/ml-baseline.json
```
Relire le taux de faux positifs et documenter ses limites (docs/05-ML-RAG.md).

## 6. Passer au réseau du groupe
Activer le point d'accès sans fil mobile Windows : nom RESILIENCE-G2,
mot de passe privé choisi par le groupe. Confirmer que l'IP Hôte du PA est bien
192.168.137.1. Dans `.env` à la racine du projet :
```dotenv
LAB_BIND=192.168.137.1
```
Recréer le WAF, puis utiliser l'IP du PA sur Hôte et Attaquant :
```bash
docker compose up -d --force-recreate waf
```
Vérifier les règles Windows Firewall avec l'équipe INFRA/CYBER. Le PC Attaquant
ne doit pas conserver une connexion parallèle au réseau du campus.
Après changement d'adresse, les scripts observateur/trafic demandent
`--url http://192.168.137.1:8081`. Le navigateur doit aussi utiliser cette URL.

## 7. Préparer le PC Attaquant
Copier seulement scripts/attack_lab.py sur ce poste. Python 3.11/3.12 :
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install httpx==0.28.1
.\.venv\Scripts\python attack_lab.py --lab-authorized --seconds 30
```
Le script demande le mot de passe du compte fictif loadbot, transmis localement
par le groupe. Ne pas copier tous les secrets sur le PC Attaquant. Sa cible par
défaut est le PC Hôte 192.168.137.1:8081 ; `--target` (ou la variable `LAB_TARGET`)
n'accepte qu'une IP littérale du sous-réseau 192.168.137.0/24 ou de loopback, tout
autre hôte est refusé. Il ne scanne rien. Scénario et bornes : docs/04-ATTAQUE.md.
Attendre que l'observateur du Hôte soit prêt avant de lancer l'attaque.

Sur Hôte, lancer d'abord :
```bash
python scripts/acceptance.py --url http://192.168.137.1:8081 --seconds 55
```
Au message d'attente, lancer la commande Attaquant. Ouvrir dashboard et Grafana
à côté. Le fichier runtime/evidence/acceptance-*.json contient le résultat réel.
En cas de FAIL, ne pas corriger pendant le live ; analyser ensuite et répéter.

## 8. Sauvegarder et arrêter sans effacer
```bash
python scripts/backup.py
docker compose stop
# Pour reprendre :
docker compose start
```
Ne pas utiliser `down -v` : cette option efface les données et preuves des volumes.
La restauration est décrite dans docs/08-PCA-PRA.md et remplace les données.

## Dépannage ciblé
- Docker absent sous WSL : vérifier Docker Desktop démarré et intégration Ubuntu.
- Port 8081 injoignable après LAB_BIND : PA actif et bonne interface, recréer WAF.
- API pas prête : logs DB/payment, mounts secrets, droits et espace disque.
- ML en attente : baseline absente ; lancer trafic normal et entraînement.
- Erreur télémétrie : cibles Prometheus, Alloy, labels service/event et disponibilité Loki.
- Alerte mais failed : playbook/control, accès WAF depuis le moteur, DB et registres.
- **Ansible « Failed to create temporary directory »** : le remédiateur a sa racine en lecture
  seule et Ansible résout `~` via la base passwd (`/home/app`), pas via `$HOME`. Les variables
  `ANSIBLE_HOME`, `ANSIBLE_LOCAL_TEMP` et `ANSIBLE_REMOTE_TEMP` doivent pointer sous `/tmp`
  (c'est fait dans `compose.yaml`). Attention : `--syntax-check` réussit même quand c'est cassé ;
  pour vraiment tester, exécuter un module :
  `docker compose exec remediator python -m ansible.cli.adhoc localhost -i localhost, -c local -m ansible.builtin.ping`
- **Grafana injoignable sur 127.0.0.1:3000 alors que le conteneur tourne** : un conteneur attaché
  uniquement à un réseau `internal: true` ne peut pas publier de port ; Docker accepte la
  déclaration et n'établit jamais le binding (`docker inspect` montre `NetworkSettings.Ports` vide).
  Grafana est donc aussi sur le réseau `mgmt`, non interne. Vérifier avec
  `docker ps --filter name=grafana --format '{{.Ports}}'` : il doit afficher `127.0.0.1:3000->3000/tcp`.
- **`init_secrets.py` : permissions POSIX non applicables** : normal si le dépôt est sur `/mnt/c`
  (volume Windows monté dans WSL). Le script le signale et continue ; la protection vient du profil
  NTFS, de `.gitignore` et de l'exclusion dans l'archive.
- Aucun 503 pendant la charge : scénario non démontré ; revoir saturation observée,
  cadence et départ des fenêtres, sans augmenter le périmètre ou dépasser les bornes.
- RAG 503 : modèle téléchargé, RAM, logs Ollama et URL du PC IA si utilisé.

Sources officielles :
- https://docs.docker.com/desktop/setup/install/windows-install/
- https://docs.docker.com/desktop/features/wsl/
- https://docs.docker.com/compose/how-tos/use-secrets/
- https://github.com/coreruleset/modsecurity-crs-docker
- https://grafana.com/docs/alloy/latest/tutorials/send-logs-to-loki/
- https://docs.langchain.com/oss/python/integrations/providers/ollama/
