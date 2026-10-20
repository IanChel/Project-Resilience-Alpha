# Lancer la recette depuis le dashboard

Le bouton du dashboard pilote uniquement l'observateur côté Hôte. Il ne lance
jamais `attack_lab.py` : le PC Attaquant reste une action manuelle.

## Préparer

1. Vérifier que Docker Desktop et la stack fonctionnent, que le PC Attaquant
   n'envoie plus de charge et que le navigateur est ouvert sur le dashboard
   avec le compte opérateur `alice`.
2. Dans PowerShell sur le PC Hôte, depuis la racine du dépôt, démarrer le pont
   local et laisser cette fenêtre ouverte :

   ```powershell
   py -3.12 scripts/recette_bridge.py
   ```

   Le pont écoute uniquement sur `127.0.0.1:8765`. Si Chrome demande l'accès au
   réseau local, l'autoriser pour le dashboard du laboratoire.

## Exécuter

1. Dans le panneau **Recette**, cliquer sur **Réinitialiser et démarrer la recette**.
2. Confirmer que l'attaque précédente est arrêtée et accepter le redémarrage de
   `payment`. Le bouton supprime uniquement `/state/policy.json`, redémarre le
   service puis vérifie le WAF avec `/api/ready`.
3. Quand le panneau et le terminal indiquent que l'observateur est prêt, lancer
   manuellement `attack_lab.py` sur le PC Attaquant.
4. Laisser acceptance puis les checks se terminer. Le panneau affiche les états
   et leurs résultats; il ne déclare la reprise validée qu'avec une transaction
   témoin et le registre à 200 000 centimes.

Le parcours lance `check_mardi.py` sur la fenêtre récente et appelle
`check_mercredi.py` avec le chemin explicite de la nouvelle preuve acceptance.
Si acceptance n'écrit pas de nouvelle preuve, le check mercredi est marqué
**NON VÉRIFIÉ** au lieu de réutiliser une ancienne preuve.

Ne pas lancer un nouvel essai avant l'arrêt de l'attaque et la conservation des
preuves de l'essai précédent. Le pont n'expose ni commande libre, ni accès au
socket Docker, et ne peut pas lancer le script d'attaque.
