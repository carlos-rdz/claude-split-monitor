#!/usr/bin/env python3
"""
claude-split cowork monitor.
Port 7433 — GET / → dashboard.html, GET /api/state → JSON, GET /api/health, WS /ws → push on change.
Polls .claude/split/inbox-planner.md + inbox-executor.md every 2s.
"""
import asyncio, json, os, re, time
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path

try:
    from websockets.asyncio.server import serve
except ImportError:
    raise SystemExit("[!] pip install 'websockets>=14'")

PORT         = 7433
HERE         = Path(__file__).parent
SESSIONS_DIR = Path.home() / ".claude" / "sessions"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
SERVER_START = time.time()

# Model pricing $/1M tokens (input, output)
_PRICING = {
    'opus':   (15.0, 75.0),
    'sonnet': (3.0,  15.0),
    'haiku':  (0.25,  1.25),
}

def _model_cost(model, t_in, t_out):
    m = model.lower()
    for key, (r_in, r_out) in _PRICING.items():
        if key in m:
            return (t_in * r_in + t_out * r_out) / 1_000_000
    return (t_in * 3.0 + t_out * 15.0) / 1_000_000  # default sonnet

# ── Inbox discovery ───────────────────────────────────────────────────────────

def find_split_dir():
    candidates = [Path.cwd() / ".claude" / "split"]
    if PROJECTS_DIR.exists():
        for p in PROJECTS_DIR.iterdir():
            if p.is_dir():
                real = Path("/") / p.name.replace("-", "/")
                candidates.append(real / ".claude" / "split")
    for c in candidates:
        if (c / "inbox-planner.md").exists() or (c / "inbox-executor.md").exists():
            return c
    return None

# ── Inbox parsing (mirrors state.js parseInbox) ───────────────────────────────

def parse_inbox(text):
    msgs = []
    for block in re.split(r'(?=^## MSG-)', text, flags=re.MULTILINE):
        if not block.strip().startswith("## MSG-"):
            continue
        def get(pat, default=""):
            m = re.search(pat, block)
            return m.group(1) if m else default
        msg_id   = block.split('\n')[0].replace('## ', '').strip()
        meta_end = block.find('\n\n')
        raw_body = block[meta_end:].strip() if meta_end != -1 else ''
        ack_match = re.search(r'\[ACK - ([^\]]+)\]', block)
        body = re.sub(r'\[ACK - [^\]]+\]', '', raw_body).strip().rstrip('-').strip()
        msgs.append({
            'id':      msg_id,
            'from':    get(r'\*\*From:\*\*\s*(\S+)'),
            'type':    get(r'\*\*Type:\*\*\s*(\S+)', 'task'),
            'priority': get(r'\*\*Priority:\*\*\s*(\S+)', 'p1'),
            'body':    body,
            'acked':   bool(ack_match),
            'ackedBy': ack_match.group(1) if ack_match else None,
        })
    return msgs

# ── MSG id → readable time ────────────────────────────────────────────────────

def msg_time(msg_id):
    m = re.search(r'MSG-(\d{8})-(\d+)', msg_id)
    if m:
        try:
            dt = datetime.strptime(m.group(1), '%Y%m%d')
            return f"{dt.strftime('%b %d')} #{int(m.group(2))}"
        except ValueError:
            pass
    return msg_id

# ── Session intelligence ──────────────────────────────────────────────────────

def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False

def _jsonl_for_cwd(cwd):
    """Find most-recent main session JSONL for a given working directory."""
    sanitized = str(Path(cwd)).lstrip('/').replace('/', '-')
    project_dir = PROJECTS_DIR / sanitized
    if not project_dir.exists():
        return None
    files = [f for f in project_dir.glob('*.jsonl') if 'subagent' not in f.name]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None

def _parse_jsonl_tail(jsonl_path, tail=600, activity_window_s=60):
    """Read last `tail` lines of a session JSONL. Return token totals + activity."""
    tokens_in = tokens_out = 0
    cost_usd   = 0.0
    activity   = []
    cutoff_ms  = (time.time() - activity_window_s) * 1000

    try:
        lines = open(jsonl_path).readlines()[-tail:]
    except Exception:
        return {'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0, 'activity': []}

    for line in lines:
        try:
            raw = json.loads(line)
        except Exception:
            continue
        if raw.get('type') != 'assistant':
            continue
        msg   = raw.get('message', {})
        usage = msg.get('usage', {})
        t_in  = usage.get('input_tokens', 0)
        t_out = usage.get('output_tokens', 0)
        model = msg.get('model', '')
        tokens_in  += t_in
        tokens_out += t_out
        cost_usd   += _model_cost(model, t_in, t_out)

        # Activity from recent turns only
        ts = raw.get('timestamp', 0)
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp() * 1000
            except Exception:
                ts = 0
        if ts >= cutoff_ms:
            for block in (msg.get('content') or []):
                btype = block.get('type', '')
                if btype == 'thinking':
                    activity.append('thinking')
                elif btype == 'tool_use':
                    name = block.get('name', '')
                    activity.append('edit' if name in ('Write', 'Edit') else
                                    'bash' if name == 'Bash' else 'tool')

    return {
        'tokens_in':  tokens_in,
        'tokens_out': tokens_out,
        'cost_usd':   round(cost_usd, 4),
        'activity':   activity[-20:],
    }

def gather_session_intel(split_dir):
    """Scan sessions, return per-role alive + token/cost/activity data."""
    roles = {'planner': {}, 'executor': {}}
    if not split_dir or not SESSIONS_DIR.exists():
        return roles
    project_root = split_dir.parent.parent
    executor_wt  = project_root / ".claude" / "worktrees" / "executor"

    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            pid  = data.get("pid")
            cwd  = data.get("cwd", "")
            if not pid or not _pid_alive(pid):
                continue
            role = ('executor' if str(Path(cwd)).startswith(str(executor_wt))
                    else 'planner' if str(Path(cwd)).startswith(str(project_root))
                    else None)
            if not role:
                continue
            jsonl = _jsonl_for_cwd(cwd)
            intel = _parse_jsonl_tail(jsonl) if jsonl else {'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0, 'activity': []}
            roles[role] = {'alive': True, **intel}
        except Exception:
            continue

    for role in roles:
        if not roles[role]:
            roles[role] = {'alive': False, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0, 'activity': []}

    return roles

# ── State builder ─────────────────────────────────────────────────────────────

def compute_state():
    split_dir = find_split_dir()
    state = {
        'type':     'cowork_state',
        'status':   'idle',
        'planner':  {'pending': [], 'done': []},
        'executor': {'pending': [], 'done': []},
        'flow':     [],
        'totals':   {'messages': 0, 'pending': 0, 'done': 0, 'total_cost': 0.0,
                     'uptime_s': int(time.time() - SERVER_START), 'sequential_estimate': 0.0},
        'split_dir':  str(split_dir) if split_dir else None,
        'updated_at': int(time.time() * 1000),
    }
    if not split_dir:
        return state

    all_msgs = []
    for role in ('planner', 'executor'):
        inbox = split_dir / f'inbox-{role}.md'
        if not inbox.exists():
            continue
        writer = 'executor' if role == 'planner' else 'planner'
        for m in parse_inbox(inbox.read_text()):
            state[role]['done' if m['acked'] else 'pending'].append(m)
            all_msgs.append({
                'id': m['id'], 'time': msg_time(m['id']),
                'from': m['from'] or writer, 'to': role,
                'type': m['type'], 'priority': m['priority'],
                'body': m['body'][:120], 'acked': m['acked'],
            })

    all_msgs.sort(key=lambda m: m['id'])
    state['flow'] = all_msgs

    total_pending = len(state['planner']['pending']) + len(state['executor']['pending'])
    total_done    = len(state['planner']['done'])    + len(state['executor']['done'])
    state['status'] = 'active' if total_pending > 0 else 'idle'

    intel = gather_session_intel(split_dir)
    for role in ('planner', 'executor'):
        state[role].update(intel[role])

    total_cost = intel['planner'].get('cost_usd', 0) + intel['executor'].get('cost_usd', 0)
    state['totals'].update({
        'messages': len(all_msgs),
        'pending':  total_pending,
        'done':     total_done,
        'total_cost': round(total_cost, 4),
        'sequential_estimate': round(total_cost * 2, 4),
    })
    # Flat alive flags for backward compat with dashboard
    state['planner_alive']  = intel['planner'].get('alive', False)
    state['executor_alive'] = intel['executor'].get('alive', False)

    return state

# ── WebSocket broadcast ───────────────────────────────────────────────────────

clients: set = set()
_last_key = None

async def broadcast(data):
    if not clients:
        return
    msg = json.dumps(data)
    dead = set()
    for ws in list(clients):
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)

async def poll_loop():
    global _last_key
    while True:
        state = compute_state()
        key = json.dumps({k: v for k, v in state.items() if k != 'updated_at'}, sort_keys=True)
        if key != _last_key:
            _last_key = key
            await broadcast(state)
            t = state['totals']
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                  f"planner {'●' if state['planner_alive'] else '○'} "
                  f"{len(state['planner']['pending'])}p/{len(state['planner']['done'])}d  "
                  f"executor {'●' if state['executor_alive'] else '○'} "
                  f"{len(state['executor']['pending'])}p/{len(state['executor']['done'])}d  "
                  f"cost=${t['total_cost']:.4f}")
        await asyncio.sleep(2)

# ── HTTP + WebSocket handler ──────────────────────────────────────────────────

async def process_request(connection, request):
    if request.path in ('/', ''):
        html = HERE / 'dashboard.html'
        body = html.read_text() if html.exists() else '<h1>dashboard.html not found</h1>'
        r = connection.respond(HTTPStatus.OK, body)
        r.headers['Content-Type'] = 'text/html; charset=utf-8'
        return r
    if request.path == '/api/state':
        r = connection.respond(HTTPStatus.OK, json.dumps(compute_state()))
        r.headers['Content-Type'] = 'application/json'
        return r
    if request.path == '/api/health':
        split_dir = find_split_dir()
        intel = gather_session_intel(split_dir) if split_dir else {}
        payload = json.dumps({
            'ok': True,
            'split_dir': str(split_dir) if split_dir else None,
            'uptime_s': int(time.time() - SERVER_START),
            'sessions_alive': {
                'planner':  intel.get('planner',  {}).get('alive', False),
                'executor': intel.get('executor', {}).get('alive', False),
            },
        })
        r = connection.respond(HTTPStatus.OK, payload)
        r.headers['Content-Type'] = 'application/json'
        return r

async def ws_handler(websocket):
    clients.add(websocket)
    print(f"  [+] client {websocket.remote_address} ({len(clients)} connected)")
    try:
        await websocket.send(json.dumps(compute_state()))
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        clients.discard(websocket)
        print(f"  [-] client disconnected ({len(clients)} total)")

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    import socket as _s
    sock = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        sock.close()

    split_dir = find_split_dir()
    print(f"\n  claude-split cowork monitor")
    print(f"  Dashboard : http://{ip}:{PORT}/")
    print(f"  State API : http://{ip}:{PORT}/api/state")
    print(f"  Health    : http://{ip}:{PORT}/api/health")
    print(f"  WebSocket : ws://{ip}:{PORT}/ws")
    print(f"  Watching  : {split_dir or 'no inbox found — will retry'}\n")

    async with serve(ws_handler, "0.0.0.0", PORT, process_request=process_request):
        await poll_loop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  [*] Shutting down.")
