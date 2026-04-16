# claude-split-monitor

**Real-time dashboard for [claude-split](https://github.com/carlos-rdz/claude-split) sessions.**

```
┌─────────────────────────────────────────────┐
│  claude-split                    ● ACTIVE   │
├──────────────────┬──────────────────────────┤
│  PLANNER         │  EXECUTOR               │
│  1 pending       │  2 pending              │
│  [RSLT] Codes..  │  [TASK] Fix disc.. !!   │
│                  │  [TASK] Add consent      │
│  Done: 3         │  Done: 1                │
├──────────────────┴──────────────────────────┤
│  MESSAGE FLOW                               │
│  planner → executor  TASK  Fix discount..   │
│  planner → executor  TASK  Add consent..    │
│  executor → planner  RSLT  Codes fixed.     │
└─────────────────────────────────────────────┘
```

## What it does

Watches your `claude-split` inbox files and shows a live web dashboard:

- **Two agent panels** — Planner (blue) and Executor (yellow) with pending/done counts
- **Pending tasks** with type badges (`TASK`, `RSLT`, `ASK?`, `BLCK`) and priority flags (`!!` for p0)
- **Message flow** — chronological log of all messages between agents
- **Live updates** — WebSocket pushes changes every 2 seconds
- **Status indicator** — green (all ACK'd), yellow (work pending), red (blocked)

## Quick Start

```bash
# In your project repo (where you ran claude-split init):
pip install websockets
python3 server.py
```

Opens at **http://localhost:7433**

## Requirements

- Python 3.8+
- `websockets` (>= 14)
- A repo with `claude-split` initialized (`.claude/split/` directory exists)

## How It Works

The server polls `.claude/split/inbox-planner.md` and `.claude/split/inbox-executor.md` every 2 seconds. When messages change, it broadcasts the full state via WebSocket to the dashboard.

```
.claude/split/inbox-*.md  →  server.py  →  WebSocket  →  dashboard.html
     (files)                 (poll 2s)      (push)        (browser)
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Serves the dashboard |
| `GET /api/state` | JSON state (same shape as WebSocket) |
| `WS /ws` | Live state updates on change |

### State Shape

```json
{
  "type": "cowork_state",
  "status": "active",
  "planner": {
    "pending": [{ "id": "MSG-...", "type": "result", "body": "..." }],
    "done": [{ "id": "MSG-...", "body": "...", "ackedBy": "planner" }]
  },
  "executor": {
    "pending": [...],
    "done": [...]
  },
  "flow": [
    { "time": "20260416-001", "from": "planner", "to": "executor", "type": "task", "body": "..." }
  ]
}
```

## Standalone Usage

The monitor auto-discovers your inbox files by scanning:
1. Current working directory (`.claude/split/`)
2. `~/.claude/projects/*/` directories

Just run `python3 server.py` from anywhere — it finds the active split session.

## License

MIT
