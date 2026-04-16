# claude-split-monitor — Claude Code Context

## What this product is

Live dashboard + native macOS app that monitors two parallel Claude Code sessions running the [claude-split](https://github.com/carlos-rdz/claude-split) coordination protocol. Python server (port 7433) parses inbox files + session JSONLs; HTML dashboard renders a swim-lane view of the collaboration.

- `pip install claude-split-monitor` → CLI `claude-split-monitor` starts server + opens browser
- Native macOS app in `app/ClaudeSplit/` (SwiftUI + WKWebView)

## Stack

- Python 3 stdlib (`websockets` dep)
- HTML/CSS/vanilla JS dashboard
- Swift Package Manager (no Xcode) for the macOS app

## Key files

- `claude_split_monitor/server.py` — data server (ingest, WS, HTTP API)
- `claude_split_monitor/dashboard.html` — swim-lane UI
- `app/ClaudeSplit/Sources/ClaudeSplit/` — native app (WatchClient + WebView + App)
- `HANDOFF.md` — latest session state (read on every resume)
- `ROADMAP.md` — phase plan
- `.claude/cowork.md` — two-instance coordination protocol

## Cowork (two instances running)

On every session start, before any other work:

1. Read `HANDOFF.md` — state of the product
2. Read `.claude/cowork.md` — protocol
3. Read **both** inboxes: `.claude/inbox/terminal.md` and `.claude/inbox/desktop.md`
4. Determine your role:
   - Worktree / isolated branch → **Terminal** (owns server.py, WatchClient.swift, back-end)
   - `main` branch with browser access → **Desktop** (owns dashboard.html, ClaudeSplitApp.swift, visual QA)
5. Post a `status` MSG to the **other** instance's inbox declaring yourself
6. Wait for their reply before picking up new work
7. Run `CronCreate` every 3 minutes to poll your inbox

Never edit a file the other instance owns.
