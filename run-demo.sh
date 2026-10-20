#!/usr/bin/env bash
# Reset the demo to a clean state BETWEEN two takes (carte J3). Never during a live take.
#
#   ./run-demo.sh reset     # lift the containment and get back to a serviceable state (default)
#   ./run-demo.sh status    # read-only: is the lab ready for a take?
#
# What a reset does, following docs/09-RECETTE-RENDU.md:
#   - stop your offensive traffic yourself first, and keep the evidence;
#   - delete /state/policy.json in payment (the containment policy persists across a recovery);
#   - restart payment and wait for /api/ready (the quote/payment series are re-created at startup);
#   - wait for the telemetry windows (10 s) and the detector cooldown (30 s) to clear;
#   - verify: containment off, series present, detector still monitoring.
# What it NEVER does: `docker compose down -v` (that wipes the ledger), clearing past incidents
#   (acceptance.py tells new ones apart), or touching the trained model, the secrets or the registry.
set -uo pipefail
export MSYS_NO_PATHCONV=1            # keep /state/... from being rewritten to a Windows path by Git Bash
cd "$(dirname "$0")"
COMPOSE=(docker compose -f compose.yaml)
COOLDOWN="${DEMO_COOLDOWN:-35}"      # seconds to wait for telemetry windows + alert cooldown; 0 to skip
ok(){ printf '  \033[32mOK\033[0m   %s\n' "$1"; }
warn(){ printf '  \033[33mATTENTION\033[0m %s\n' "$1"; }
die(){ printf '  \033[31mECHEC\033[0m %s\n' "$1" >&2; exit 1; }
exec_payment(){ "${COMPOSE[@]}" exec -T payment python -c "$1" 2>/dev/null; }

running(){ [ "$("${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -c '^payment$')" = 1 ]; }
metric(){ exec_payment "import urllib.request
for l in urllib.request.urlopen('http://localhost:8000/metrics',timeout=5).read().decode().splitlines():
    if l.startswith('$1'): print(l.split()[1]); break"; }
ready(){ exec_payment "import urllib.request,sys
try: sys.exit(0 if urllib.request.urlopen('http://localhost:8000/ready',timeout=3).status==200 else 1)
except Exception: sys.exit(1)"; }
detector_status(){ "${COMPOSE[@]}" exec -T detector python -c "import urllib.request,json
print(json.loads(urllib.request.urlopen('http://localhost:8000/anomaly',timeout=5).read().decode())['status'])" 2>/dev/null; }

check_series(){
  local q p; q=$(metric 'lab_requests_total{route="quotes"'); p=$(metric 'lab_requests_total{route="payments"')
  [ -n "$q" ] && [ -n "$p" ] && ok "series quotes et payments presentes" || die "series applicatives absentes (payment pas (re)demarre avec le code a jour ?)"
}
check_detector(){
  local s; s=$(detector_status)
  case "$s" in
    monitoring) ok "detecteur en monitoring (modele charge)";;
    waiting_for_trained_model) warn "detecteur sans modele entraine : la detection ne marchera pas. Entrainer (docs/05-ML-RAG.md, phase 1).";;
    telemetry_or_delivery_error) warn "detecteur en erreur de collecte : verifier Prometheus/Loki (il se retablit apres du trafic).";;
    *) warn "detecteur: etat inattendu '${s:-injoignable}'";;
  esac
}

cmd_status(){
  echo "Etat du laboratoire :"
  running || die "le service payment ne tourne pas : docker compose up -d"
  ready && ok "payment repond (/ready 200)" || die "payment ne repond pas sur /ready"
  local c; c=$(metric 'lab_contained')
  [ "$c" = "0.0" ] && ok "pas de confinement actif" || warn "confinement ACTIF (lab_contained=$c) : lancer ./run-demo.sh reset avant la prochaine prise"
  check_series; check_detector
  echo "Pret pour une prise si tout est OK ci-dessus."
}

cmd_reset(){
  echo "Reset de la demo (entre deux prises) :"
  running || die "le service payment ne tourne pas : docker compose up -d"
  exec_payment "from pathlib import Path; Path('/state/policy.json').unlink(missing_ok=True)" && ok "policy.json supprime (confinement leve)" || die "suppression de policy.json impossible"
  echo "  redemarrage de payment..."; "${COMPOSE[@]}" restart payment >/dev/null 2>&1 || die "redemarrage de payment en echec"
  local i; for i in $(seq 1 30); do ready && break; sleep 1; [ "$i" = 30 ] && die "payment ne repond pas sur /ready apres 30 s"; done
  ok "payment repond a nouveau (/ready 200)"
  local c; c=$(metric 'lab_contained'); [ "$c" = "0.0" ] && ok "confinement leve (lab_contained=0.0)" || die "confinement toujours actif apres reset (lab_contained=$c)"
  check_series
  if [ "$COOLDOWN" -gt 0 ]; then echo "  attente de $COOLDOWN s (fenetres de telemetrie 10 s + refroidissement alerte 30 s)..."; sleep "$COOLDOWN"; ok "fenetres et refroidissement ecoules"; fi
  check_detector
  echo "Reset termine. Lancer l'observateur puis l'attaque pour une nouvelle prise (docs/INSTALL.md)."
}

case "${1:-reset}" in
  reset) cmd_reset;;
  status|check) cmd_status;;
  *) echo "usage: $0 [reset|status]" >&2; exit 2;;
esac
