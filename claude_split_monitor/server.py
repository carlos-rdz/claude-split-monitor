#!/usr/bin/env python3
"""
claude-split cowork monitor.
Port 7433 — GET / → dashboard.html, GET /api/state → JSON, GET /api/health, WS /ws → push on change.
Polls .claude/split/inbox-planner.md + inbox-executor.md every 2s.
"""
import asyncio, json, os, re, subprocess, time
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
HISTORY_DIR  = Path.home() / ".claude-split" / "history"
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

def _inbox_mtime(split_dir):
    """Return mtime of the most recently modified inbox file in split_dir."""
    best = 0.0
    for name in ('inbox-planner.md', 'inbox-executor.md'):
        p = split_dir / name
        try:
            best = max(best, p.stat().st_mtime)
        except OSError:
            pass
    return best

def find_split_dir():
    # Explicit env override
    env = os.environ.get('CLAUDE_SPLIT_DIR')
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    # CWD takes priority when running from inside a project
    cwd_candidate = Path.cwd() / ".claude" / "split"

    # Collect all valid dirs — each session JSONL dir encodes the original CWD
    # as a sanitized name: leading '/' stripped, remaining '/' → '-'.
    # We cannot safely reverse that (hyphens are ambiguous), so instead we read
    # ~/.claude/sessions/*.json for live CWDs, then fall back to filesystem scan.
    valid = []

    # Live sessions first
    if SESSIONS_DIR.exists():
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                cwd = json.loads(f.read_text()).get("cwd", "")
                if not cwd:
                    continue
                sd = Path(cwd) / ".claude" / "split"
                if sd.is_dir() and ((sd / "inbox-planner.md").exists() or
                                     (sd / "inbox-executor.md").exists()):
                    valid.append(sd)
            except Exception:
                continue

    # CWD candidate
    if (cwd_candidate / "inbox-planner.md").exists() or \
       (cwd_candidate / "inbox-executor.md").exists():
        valid.append(cwd_candidate)

    # Deduplicate
    seen = set()
    unique = []
    for v in valid:
        k = str(v.resolve())
        if k not in seen:
            seen.add(k)
            unique.append(v)

    if not unique:
        return None
    if len(unique) == 1:
        return unique[0]

    # Multiple matches — prefer most recently modified inbox
    return max(unique, key=_inbox_mtime)

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

def _classify_tool(name):
    if name == 'Read':                            return 'Read'
    if name in ('Write', 'Edit', 'NotebookEdit'): return 'Edit'
    if name == 'Bash':                            return 'Bash'
    if name in ('Grep', 'Glob'):                  return 'Search'
    return 'Tool'

def _parse_ts(raw_ts):
    """Parse a JSONL timestamp to milliseconds since epoch."""
    if isinstance(raw_ts, str):
        try:
            return int(datetime.fromisoformat(raw_ts.replace('Z', '+00:00')).timestamp() * 1000)
        except Exception:
            return 0
    if isinstance(raw_ts, (int, float)):
        # Already ms if > 1e12, else seconds
        return int(raw_ts * 1000) if raw_ts < 1e12 else int(raw_ts)
    return 0

def _parse_jsonl_tail(jsonl_path, tail=600, activity_window_s=60):
    """Read last `tail` lines of a session JSONL. Return token totals + activity + recent actions."""
    _empty = {
        'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0, 'activity': [],
        'recent_actions': [], 'last_action': None, 'files_edited': 0,
    }
    tokens_in = tokens_out = 0
    cost_usd      = 0.0
    activity      = []
    all_actions   = []   # {type, target, at} — all, sorted later
    files_edited  = set()
    cutoff_ms     = (time.time() - activity_window_s) * 1000

    try:
        lines = open(jsonl_path).readlines()[-tail:]
    except Exception:
        return _empty

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

        ts_ms = _parse_ts(raw.get('timestamp', 0))

        for block in (msg.get('content') or []):
            btype = block.get('type', '')
            if btype == 'thinking':
                snippet = (block.get('thinking') or '')[:80]
                all_actions.append({'type': 'Think', 'target': snippet, 'at': ts_ms})
                if ts_ms >= cutoff_ms:
                    activity.append('thinking')
            elif btype == 'tool_use':
                name   = block.get('name', '')
                inp    = block.get('input') or {}
                atype  = _classify_tool(name)
                target = (inp.get('file_path') or inp.get('path') or
                          inp.get('pattern')   or inp.get('command') or
                          inp.get('query')     or name)
                target = str(target)[:120] if target else name
                all_actions.append({'type': atype, 'target': target, 'at': ts_ms})
                if atype == 'Edit':
                    fp = inp.get('file_path', '')
                    if fp:
                        files_edited.add(fp)
                if ts_ms >= cutoff_ms:
                    activity.append(
                        'edit' if atype == 'Edit' else
                        'bash' if atype == 'Bash' else 'tool'
                    )

    all_actions.sort(key=lambda a: a['at'], reverse=True)
    return {
        'tokens_in':      tokens_in,
        'tokens_out':     tokens_out,
        'cost_usd':       round(cost_usd, 4),
        'activity':       activity[-20:],
        'recent_actions': all_actions[:5],
        'last_action':    all_actions[0] if all_actions else None,
        'files_edited':   len(files_edited),
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
            roles[role] = {
                'alive': False, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0,
                'activity': [], 'recent_actions': [], 'last_action': None, 'files_edited': 0,
            }

    return roles


# ── Git log ───────────────────────────────────────────────────────────────────

def _git_commits(project_root, limit=10):
    """Return last `limit` commits with numstat diff totals."""
    try:
        result = subprocess.run(
            ['git', 'log', '--numstat', f'-{limit}', '--format=COMMIT %H %at %s'],
            cwd=str(project_root), capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
    except Exception:
        return []

    commits = []
    current = None
    for line in result.stdout.splitlines():
        if line.startswith('COMMIT '):
            if current:
                commits.append(current)
            parts = line[7:].split(' ', 2)
            current = {
                'sha':         parts[0][:7] if parts else '',
                'at':          int(parts[1]) * 1000 if len(parts) > 1 and parts[1].isdigit() else 0,
                'msg':         parts[2] if len(parts) > 2 else '',
                'added':       0,
                'removed':     0,
                'author_role': None,
            }
        elif current and line.strip() and '\t' in line:
            parts = line.split('\t')
            if len(parts) >= 2:
                try:
                    current['added']   += int(parts[0]) if parts[0].isdigit() else 0
                    current['removed'] += int(parts[1]) if parts[1].isdigit() else 0
                except Exception:
                    pass
    if current:
        commits.append(current)
    return commits

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

    # stuck_seconds + alerts
    now_ms = time.time() * 1000
    alerts = []
    for role in ('planner', 'executor'):
        last_act = state[role].get('last_action')
        if last_act and last_act.get('at'):
            stuck_s = int((now_ms - last_act['at']) / 1000)
            state[role]['stuck_seconds'] = max(stuck_s, 0)
            if state[role].get('alive') and stuck_s > 120:
                m, s = divmod(stuck_s, 60)
                alerts.append({
                    'severity': 'warn',
                    'agent':    role,
                    'text':     f"stuck {m}m {s}s",
                    'since':    last_act['at'],
                })
        else:
            state[role]['stuck_seconds'] = 0
    state['alerts'] = alerts

    # Git commits from project root
    if split_dir:
        project_root = split_dir.parent.parent
        state['git'] = {'commits': _git_commits(project_root)}

    return state

# ── Session history (Phase 5) ────────────────────────────────────────────────

def _session_snapshot(state):
    """Minimal summary dict for history records."""
    t = state.get('totals', {})
    return {
        'ts':         int(time.time()),
        'iso':        datetime.now(timezone.utc).isoformat(),
        'split_dir':  state.get('split_dir'),
        'status':     state.get('status', 'idle'),
        'messages':   t.get('messages', 0),
        'pending':    t.get('pending', 0),
        'done':       t.get('done', 0),
        'total_cost': t.get('total_cost', 0.0),
        'uptime_s':   t.get('uptime_s', 0),
        'planner_alive':  state.get('planner_alive', False),
        'executor_alive': state.get('executor_alive', False),
    }

_session_file: Path | None = None
_last_saved_key: str | None = None

def save_history(state):
    """Append snapshot to ~/.claude-split/history/{session_start}.jsonl."""
    global _session_file, _last_saved_key
    snap = _session_snapshot(state)
    key  = json.dumps({k: v for k, v in snap.items() if k not in ('ts', 'iso', 'uptime_s')})
    if key == _last_saved_key:
        return
    _last_saved_key = key
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        if _session_file is None:
            _session_file = HISTORY_DIR / f"{int(SERVER_START)}.jsonl"
        with open(_session_file, 'a') as f:
            f.write(json.dumps(snap) + '\n')
    except Exception:
        pass

def load_history(limit=50):
    """Read last `limit` snapshots across all session files, newest first."""
    if not HISTORY_DIR.exists():
        return []
    sessions = []
    for f in sorted(HISTORY_DIR.glob('*.jsonl'), reverse=True)[:20]:
        try:
            lines = f.read_text().strip().splitlines()
            if not lines:
                continue
            # Use last snapshot per session file as the session summary
            last = json.loads(lines[-1])
            first = json.loads(lines[0])
            sessions.append({
                'session_id': f.stem,
                'started':    first.get('iso', ''),
                'ended':      last.get('iso', ''),
                'messages':   last.get('messages', 0),
                'done':       last.get('done', 0),
                'total_cost': last.get('total_cost', 0.0),
                'uptime_s':   last.get('uptime_s', 0),
                'snapshots':  len(lines),
            })
        except Exception:
            continue
    return sessions[:limit]

def aggregate_stats():
    """Totals across all saved sessions."""
    sessions = load_history(limit=1000)
    return {
        'total_sessions':  len(sessions),
        'total_messages':  sum(s.get('messages', 0) for s in sessions),
        'total_done':      sum(s.get('done', 0) for s in sessions),
        'total_cost':      round(sum(s.get('total_cost', 0) for s in sessions), 4),
        'total_uptime_s':  sum(s.get('uptime_s', 0) for s in sessions),
    }

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
            save_history(state)
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
    if request.path == '/api/history':
        r = connection.respond(HTTPStatus.OK, json.dumps({
            'sessions': load_history(),
            'aggregate': aggregate_stats(),
        }))
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
    print(f"  History   : http://{ip}:{PORT}/api/history")
    print(f"  WebSocket : ws://{ip}:{PORT}/ws")
    print(f"  Watching  : {split_dir or 'no inbox found — will retry'}\n")

    async with serve(ws_handler, "0.0.0.0", PORT, process_request=process_request):
        await poll_loop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  [*] Shutting down.")
