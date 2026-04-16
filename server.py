#!/usr/bin/env python3
"""
claude-split cowork monitor.
Port 7433 — GET / → dashboard.html, GET /api/state → JSON, WS /ws → push on change.
Polls .claude/split/inbox-planner.md + inbox-executor.md every 2s.
"""
import asyncio, json, re, time
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

try:
    from websockets.asyncio.server import serve
except ImportError:
    raise SystemExit("[!] pip install 'websockets>=14'")

PORT = 7433
HERE = Path(__file__).parent

# ── Inbox discovery ───────────────────────────────────────────────────────────

def find_split_dir():
    candidates = [Path.cwd() / ".claude" / "split"]
    projects = Path.home() / ".claude" / "projects"
    if projects.exists():
        for p in projects.iterdir():
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
        msg_id  = block.split('\n')[0].replace('## ', '').strip()
        meta_end = block.find('\n\n')
        raw_body = block[meta_end:].strip() if meta_end != -1 else ''
        ack_match = re.search(r'\[ACK - ([^\]]+)\]', block)
        body = re.sub(r'\[ACK - [^\]]+\]', '', raw_body).strip().rstrip('-').strip()
        msgs.append({
            'id':       msg_id,
            'from':     get(r'\*\*From:\*\*\s*(\S+)'),
            'type':     get(r'\*\*Type:\*\*\s*(\S+)', 'task'),
            'priority': get(r'\*\*Priority:\*\*\s*(\S+)', 'p1'),
            'body':     body,
            'acked':    bool(ack_match),
            'ackedBy':  ack_match.group(1) if ack_match else None,
        })
    return msgs

# ── State builder ─────────────────────────────────────────────────────────────

def compute_state():
    split_dir = find_split_dir()
    state = {
        'type':     'cowork_state',
        'status':   'idle',
        'planner':  {'pending': [], 'done': []},
        'executor': {'pending': [], 'done': []},
        'flow':     [],
        'split_dir': str(split_dir) if split_dir else None,
        'updated_at': int(time.time() * 1000),
    }
    if not split_dir:
        return state

    all_msgs = []
    for role in ('planner', 'executor'):
        inbox = split_dir / f'inbox-{role}.md'
        if not inbox.exists():
            continue
        for m in parse_inbox(inbox.read_text()):
            bucket = 'done' if m['acked'] else 'pending'
            state[role][bucket].append(m)
            # flow entry: inbox-planner = executor→planner, inbox-executor = planner→executor
            writer = 'executor' if role == 'planner' else 'planner'
            all_msgs.append({
                'id':     m['id'],
                'time':   m['id'][4:] if len(m['id']) > 4 else m['id'],  # YYYYMMDD-NNN
                'from':   m['from'] or writer,
                'to':     role,
                'type':   m['type'],
                'priority': m['priority'],
                'body':   m['body'][:120],
                'acked':  m['acked'],
            })

    all_msgs.sort(key=lambda m: m['id'])
    state['flow'] = all_msgs

    total_pending = len(state['planner']['pending']) + len(state['executor']['pending'])
    state['status'] = 'active' if total_pending > 0 else 'idle'

    return state

# ── WebSocket broadcast ───────────────────────────────────────────────────────

clients: set = set()
_last_key   = None

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
            pp, pd = len(state['planner']['pending']), len(state['planner']['done'])
            ep, ed = len(state['executor']['pending']), len(state['executor']['done'])
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] planner {pp}p/{pd}d  executor {ep}p/{ed}d  status={state['status']}")
        await asyncio.sleep(2)

# ── HTTP + WebSocket handler ──────────────────────────────────────────────────

async def process_request(connection, request):
    if request.path in ('/', ''):
        html = HERE / 'dashboard.html'
        body = html.read_text() if html.exists() else '<h1>dashboard.html not found</h1>'
        response = connection.respond(HTTPStatus.OK, body)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    if request.path == '/api/state':
        body = json.dumps(compute_state())
        response = connection.respond(HTTPStatus.OK, body)
        response.headers['Content-Type'] = 'application/json'
        return response
    # /ws → fall through to WebSocket upgrade

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
        print(f"  [-] client disconnected ({len(clients)} connected)")

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    import socket as _sock
    s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()

    split_dir = find_split_dir()
    print(f"\n  claude-split cowork monitor")
    print(f"  Dashboard : http://{ip}:{PORT}/")
    print(f"  State API : http://{ip}:{PORT}/api/state")
    print(f"  WebSocket : ws://{ip}:{PORT}/ws")
    print(f"  Watching  : {split_dir or 'no inbox found — will retry every 2s'}\n")

    async with serve(ws_handler, "0.0.0.0", PORT, process_request=process_request):
        await poll_loop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  [*] Shutting down.")
