"""Loopback-only, fixed-operation bridge for the authenticated dashboard recette controls.

Run on the Windows HOST in a dedicated terminal: `py -3.12 scripts/recette_bridge.py`.
It exposes no command runner: POST /start can only start scripts/run_recette.py with fixed arguments.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
HOST = '127.0.0.1'
PORT = 8765
RUN_SECONDS = 70
API_TARGETS = ('http://192.168.137.1:8081', 'http://127.0.0.1:8081', 'http://localhost:8081')
NO_PROXY = build_opener(ProxyHandler({}))
ALLOWED_ORIGINS = frozenset(f'{host}:8081' for host in ('http://192.168.137.1', 'http://127.0.0.1', 'http://localhost'))
_guard = threading.RLock()
_state = {'status': 'idle', 'phase': 'idle', 'started_at': None, 'server_started_at': None,
          'exit_code': None, 'acceptance': None, 'check_mardi': None, 'check_mercredi': None,
          'details': [], 'result_file': None}
_process: subprocess.Popen[str] | None = None
_auth_cache: dict[str, tuple[float, str, float | None]] = {}

def origin_allowed(origin: str) -> bool:
    return origin in ALLOWED_ORIGINS

def confirmed_request(body: object) -> bool:
    return isinstance(body, dict) and body == {'confirmed': True}

def runner_argv(base: str) -> list[str]:
    # This fixed allowlist is the only operation the browser can launch.
    return [sys.executable, str(ROOT / 'scripts' / 'run_recette.py'), '--yes',
            '--seconds', str(RUN_SECONDS), '--url', base]


def _operator_target(token: str) -> tuple[str, float | None] | None:
    """Verify the bearer as an operator through the existing WAF auth boundary; never log/store it."""
    if not token or len(token) > 8192:
        return None
    digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
    now = time.monotonic()
    cached = _auth_cache.get(digest)
    if cached and cached[0] > now:
        return cached[1], cached[2]
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}
    for base in API_TARGETS:
        try:
            with NO_PROXY.open(Request(base + '/api/accounts', headers=headers), timeout=2) as response:
                if response.status != 200:
                    continue
            server_now = None
            try:
                with NO_PROXY.open(Request(base + '/ops/status', headers=headers), timeout=2) as response:
                    payload = json.loads(response.read(512_000).decode('utf-8'))
                    if isinstance(payload.get('now'), (int, float)):
                        server_now = float(payload['now'])
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                pass
            _auth_cache[digest] = (now + 15, base, server_now)
            # Keep only the short-lived active token digest; no bearer or response payload is retained.
            for key, value in tuple(_auth_cache.items()):
                if value[0] <= now:
                    _auth_cache.pop(key, None)
            return base, server_now
        except (HTTPError, URLError, TimeoutError):
            continue
    return None


def _read_token(handler: BaseHTTPRequestHandler) -> str:
    value = handler.headers.get('Authorization', '')
    if not value.startswith('Bearer '):
        return ''
    return value[7:].strip()


def _phase_from_line(line: str) -> None:
    global _process
    clean = line.strip()
    with _guard:
        marker='RECETTE_RESULT_JSON '
        if clean.startswith(marker):
            try: result=json.loads(clean[len(marker):])
            except (ValueError,TypeError): result={}
            if isinstance(result,dict):
                _state.update(status='complete' if result.get('status')=='PASS' else 'failed',
                              phase='complete' if result.get('status')=='PASS' else 'failed',
                              acceptance=result.get('acceptance'),check_mardi=result.get('check_mardi'),
                              check_mercredi=result.get('check_mercredi'),result_file=result.get('result_file'))
        # Keep only bounded, useful result/diagnostic lines for the dashboard. The runner never prints
        # credential values, but redact common sensitive fields as defense in depth before retaining output.
        if any(word in clean.casefold() for word in (
            'fail', 'echec', 'échec', 'non verifie', 'non vérifié', 'traceback', 'error',
            'ecart', 'écart', 'absent', 'aucun rejet', 'timeout', 'httpstatuserror',
            'connectionrefused', 'connecttimeout', 'unauthorized', 'forbidden',
        )):
            safe = re.sub(r'(?i)(password|token|secret|authorization)([\s"\'=:\[]+)[^\s,;\]}]+', r'\1\2[redacted]', clean)
            safe = safe.replace(str(ROOT / '.secrets'), '[secret-path]')[:500]
            details = _state.setdefault('details', [])
            if not details or details[-1] != safe:
                details.append(safe)
                del details[:-30]
        if '[1/5] Reset' in clean: _state['phase'] = 'resetting'
        elif '[2/5] Redemarrage' in clean: _state['phase'] = 'restarting'
        elif '[3/5] Attente' in clean: _state['phase'] = 'waiting_ready'
        elif '[4/5] Lancement' in clean: _state['phase'] = 'starting_observer'
        elif 'Observateur pret' in clean: _state.update(status='waiting_attack', phase='waiting_attack')
        elif '[5/5] Controles' in clean: _state.update(status='checking', phase='checking')
        elif 'check_mardi' in clean and '->' in clean:
            _state['check_mardi'] = 'PASS' if 'PASS' in clean else ('NON VÉRIFIÉ' if 'NON VERIFIE' in clean else 'FAIL')
        elif 'check_mercredi' in clean and '->' in clean:
            _state['check_mercredi'] = 'PASS' if 'PASS' in clean else ('NON VÉRIFIÉ' if 'NON VERIFIE' in clean else 'FAIL')
        elif '[acceptance] PASS' in clean: _state['acceptance'] = 'PASS'
        elif '[acceptance] FAIL' in clean: _state['acceptance'] = 'FAIL'
        elif clean.startswith('  acceptance :'):
            _state['acceptance'] = 'PASS' if 'PASS' in clean else 'FAIL'


def _watch(proc: subprocess.Popen[str]) -> None:
    global _process
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            _phase_from_line(line)
        code = proc.wait()
    except Exception:
        code = 1
    with _guard:
        if _process is proc:
            _process = None
            _state['exit_code'] = code
            _state['status'] = 'complete' if code == 0 else 'failed'
            _state['phase'] = 'complete' if code == 0 else 'failed'
            if _state.get('acceptance') is None:
                _state['acceptance'] = 'FAIL'


class Handler(BaseHTTPRequestHandler):
    server_version = 'ResilienceRecetteBridge/1'

    def log_message(self, _format: str, *args: object) -> None:
        # Requests carry bearer tokens; never write paths, headers, or request text to stdout.
        return

    def _origin_ok(self) -> bool:
        return origin_allowed(self.headers.get('Origin', ''))

    def _cors(self) -> None:
        origin = self.headers.get('Origin', '')
        if origin_allowed(origin):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Cache-Control', 'no-store')

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> tuple[str, float | None] | None:
        if not self._origin_ok():
            self._send(403, {'error': 'origin_refused'})
            return None
        auth = _operator_target(_read_token(self))
        if not auth:
            self._send(401, {'error': 'operator_auth_required'})
            return None
        return auth

    def do_OPTIONS(self) -> None:
        if not self._origin_ok():
            self.send_error(403)
            return
        self.send_response(204)
        self._cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != '/status':
            self._send(404, {'error': 'not_found'})
            return
        auth = self._authorized()
        if not auth:
            return
        with _guard:
            data = dict(_state)
        self._send(200, data)

    def do_POST(self) -> None:
        global _process
        if self.path != '/start':
            self._send(404, {'error': 'not_found'})
            return
        auth = self._authorized()
        if not auth:
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 256:
                raise ValueError
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {'error': 'invalid_request'})
            return
        if not confirmed_request(body):
            self._send(400, {'error': 'explicit_confirmation_required'})
            return
        base, server_now = auth
        with _guard:
            if _process is not None and _process.poll() is None:
                self._send(409, {'error': 'run_already_active', **_state})
                return
            _state.update(status='running', phase='starting', started_at=time.time(),
                          server_started_at=server_now, exit_code=None, acceptance=None,
                          check_mardi=None, check_mercredi=None, details=[], result_file=None)
            argv = runner_argv(base)
            try:
                _process = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                    bufsize=1, shell=False)
            except OSError:
                _process = None
                _state.update(status='failed', phase='failed', exit_code=1)
                self._send(503, {'error': 'runner_start_failed', **_state})
                return
            threading.Thread(target=_watch, args=(_process,), name='recette-watch', daemon=True).start()
        self._send(202, dict(_state))


def main() -> int:
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f'Impossible de démarrer le lanceur local sur {HOST}:{PORT} ({type(exc).__name__}).', file=sys.stderr)
        return 1
    server.daemon_threads = True
    print(f'Lanceur de recette local actif sur http://{HOST}:{PORT}. Gardez cette fenêtre ouverte; Ctrl+C pour arrêter.')
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        with _guard:
            proc = _process
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
