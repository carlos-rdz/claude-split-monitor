# Session Handoff — Read This First

**Date:** 2026-04-16
**Previous sessions:** Desktop + Terminal working in cowork mode
**Status:** Swim lane dashboard rebuilt, demo mode in progress, needs polish

---

## READ THIS BEFORE DOING ANYTHING

You are ONE of TWO Claude sessions. There's another Claude running in parallel. **Do not work alone.** Cowork instructions below.

## What this product is

**claude-split** (https://github.com/carlos-rdz/claude-split) — coordination protocol for 2 Claude sessions via inbox files. Roles: `planner` assigns tasks, `executor` implements. Messages in markdown files. No shared mutable state.

**claude-split-monitor** (https://github.com/carlos-rdz/claude-split-monitor) — live dashboard for the above.
- Python server (port 7433) parses `.claude/split/inbox-*.md` + `~/.claude/sessions/*.json` for live data
- HTML dashboard served from the same port
- Native macOS app (`app/ClaudeSplit/`) — SPM executable wrapped in `.app` bundle
- Installed via `pip install claude-split-monitor`

## Current state

### Dashboard (`claude_split_monitor/dashboard.html`) — swim lane view
- Top bar: planner badge (left) / collab state (middle) / executor badge (right)
- Toolbar: VIEW pills (both/planner/executor), search box, rate meter, live indicator
- Main: **swim lanes** — two parallel columns with vertical time axis
  - Actions anchor to their agent's column
  - Messages cross both columns with `→` / `←` arrows
  - ACKs show cycle time
  - Idle gaps >60s collapse to thin separator
- Status bar: path + keybinds
- Demo mode: `#demo=easy|medium|hard` injects synthetic events

### Server (`claude_split_monitor/server.py`)
- `GET /` → dashboard, `GET /api/state` → JSON, `GET /api/health` → ok, `WS /ws` → push on change
- Phase 3: alive detection, token/cost tracking from session JSONLs
- Phase 5: session history persistence (`~/.claude-split/history/`)
- Phase 7: recent_actions per agent, stuck_seconds, alerts[], git commits

### Native app (`app/ClaudeSplit/`)
- SwiftUI window app (NOT menu bar — user explicitly killed menu bar)
- Opens WebView showing `localhost:7433`
- Build: `cd app/ClaudeSplit && ./make-app.sh && open build/ClaudeSplit.app`

### What the founder killed/hates
- PM metrics (throughput, velocity, burndown) — "we're not a team of humans"
- Kanban columns — "same data different shape"
- Git feed — removed per founder request
- Menu bar — "i want dash" (a visible window, not a tiny icon)
- Mixed event log — "no value, i want a live feed"
- Corporate dashboard look — "horrible wtf is this"

### What the founder wants
- "Lightweight, sleek, tech tool"
- "Live feed"
- "Data rich, logical, purposeful"
- "Linus Torvalds approved" — terminal aesthetic, monospace, zero chrome
- Collab tool framing — "who's doing what together, handoffs, blockers"
- Specifically: swim lanes showing parallel work + messages as handoffs

---

## The cowork setup (THIS SESSION IS YOU)

There are 2 Claude sessions. Coordinate via these files (now local to this repo):

| File | Direction | Purpose |
|---|---|---|
| `.claude/inbox/terminal.md` | Desktop → Terminal | Tasks you assign to the other instance |
| `.claude/inbox/desktop.md` | Terminal → Desktop | Tasks the other instance assigns to you |

(Earlier sessions coordinated via `patriot-portraits/.claude/inbox/` — that history is archived in that repo's git log. All new messages go in the files above.)

**Protocol** (`.claude/cowork.md`):
- Append messages only. Never overwrite.
- Message format:
  ```
  ## MSG-YYYY-MM-DD-NNN
  **From:** desktop|terminal
  **Type:** task|result|question|block
  **Priority:** p0|p1|p2

  body

  [ACK - desktop] acknowledgment when acted on
  ```
- Read the OTHER instance's inbox before starting work (see what they're doing)
- Post updates to YOUR inbox after work
- ACK messages when you've handled them

**Your role:** Check the inboxes to figure out which role you are:
- If the last `[ACK - desktop]` is recent → you're probably Desktop
- If the last `[ACK - terminal]` is recent → you're probably Terminal
- Otherwise, declare yourself in the first message

**Split that's been working well:**
- Desktop owns: dashboard.html (UI/UX), Swift app UI, front-end work
- Terminal owns: server.py (data ingest), Swift client logic, back-end work

---

## Next session prompt (copy-paste this)

```
Read HANDOFF.md in /Users/crodriguez/code/claude-split-monitor/.

You are ONE OF TWO Claude sessions working on this product. The other Claude is running in parallel RIGHT NOW. Do NOT work alone.

Steps:
1. Read HANDOFF.md fully
2. Read .claude/cowork.md (the cowork protocol)
3. Read the latest entries in BOTH inboxes:
   - .claude/inbox/terminal.md
   - .claude/inbox/desktop.md
4. Decide which role you are (Desktop = UI/front-end, Terminal = server/back-end)
5. Post a MSG to the other instance's inbox: "I'm resuming as [role]. What's your status?"
6. Wait for their reply before picking up new work.
7. Work in parallel but NEVER on the same file. Coordinate via inbox.

Current state of the work:
- claude-split-monitor dashboard is swim-lane view
- Demo mode (#demo=easy|medium|hard) was being built but timestamps may still be glitchy
- Native macOS app works but needs more polish
- Server has all Phase 3/5/7 data fields

Immediate open tasks:
1. Fix demo mode timestamps (events rendering out of order)
2. Test each demo level (easy/medium/hard) and capture screenshots
3. Polish the swim lane rendering — handoff arrows, shared file indicators
4. Add "waiting on" badge when one agent has been stuck/waiting for >60s

DO NOT:
- Work on patriot-portraits project (that's separate, currently parked)
- Rebuild the dashboard with corporate metrics (founder hates that)
- Add a git feed back (founder killed it)
- Add a menu bar — founder wants the dashboard window
```

---

## Open tasks (priority order)

1. **Fix demo mode timestamps** — events render out of order in `#demo=easy`, should be strictly chronological per script
2. **Test all 3 demo levels** visually, capture screenshots of each
3. **Polish swim lane rendering** — currently simple, could use:
   - Colored glow on new messages (already flash animation, could be stronger)
   - Dotted line connecting consecutive actions from same agent (visual continuity)
   - Shared file indicator (if both agents touched same file, highlight both)
4. **"Waiting on" pinned banner** — when an agent has been stuck/waiting for another's response for >60s, surface it at the top
5. **Native app polish** — currently minimal; could use title bar with server status, refresh, preferences
6. **Real server integration test** — run both inbox and session JSONL parsing with actual live Claude sessions and verify events flow end-to-end

## Files to know

```
claude-split-monitor/
├── HANDOFF.md                               ← you are here
├── README.md                                 ← user-facing docs
├── ROADMAP.md                                ← phase plan (Phases 1-7 shipped)
├── pyproject.toml                            ← pip package
├── claude_split_monitor/
│   ├── __init__.py
│   ├── cli.py                                ← entry point
│   ├── server.py                             ← the data server (Terminal owns)
│   └── dashboard.html                        ← the UI (Desktop owns)
├── app/ClaudeSplit/
│   ├── Package.swift                         ← SPM manifest
│   ├── make-app.sh                           ← builds .app bundle
│   └── Sources/ClaudeSplit/
│       ├── ClaudeSplitApp.swift              ← app entry + window scene (Desktop owns)
│       ├── WatchClient.swift                 ← WebSocket client (Terminal owns)
│       └── WebView.swift                     ← WKWebView wrapper
└── docs/
    ├── screenshot.png                        ← hero screenshot
    └── index.html                            ← GitHub Pages landing
```

## Known issues

- Demo mode timestamps render events out of script order (see screenshot in Chrome at localhost:7433/#demo=easy)
- Dashboard's `ingest()` pulls messages via arrival time; demo pushes directly with proper `at` which works but needs verification
- Server's `find_split_dir()` can match wrong project dir if multiple have `.claude/split/`

## What's working

- ✅ pip install claude-split-monitor
- ✅ `claude-split-monitor` CLI starts server + opens browser
- ✅ WebSocket live updates
- ✅ Session alive detection, token tracking, cost estimation
- ✅ `/api/health`, `/api/state`, `/api/history` endpoints
- ✅ Native macOS `.app` bundle
- ✅ Swim lane rendering for real data
- ✅ Keyboard shortcuts (B/P/E/F/`/`)

## Last commits

```
a318619 refactor(dashboard): unified live event feed (devtools style)
37c58fd feat(app): make-app.sh + .gitignore for Swift build artifacts
5a7fb67 feat(app): make-app.sh packages SPM binary as ClaudeSplit.app bundle
e3f3caa fix(app): guard UNUserNotificationCenter behind bundle check
06d0f93 feat(app): WatchClient + WebView — Swift menu bar client
85922f4 scaffold: native macOS menu-bar app (SwiftUI)
```

(The latest dashboard rewrite to swim lanes is local, not yet committed — commit it first thing.)

---

## If this session runs out of tokens

Write an append to this HANDOFF.md with:
- What you shipped
- What you attempted and didn't finish
- Next steps
Commit and push. Do NOT leave state on disk that's not in git.
