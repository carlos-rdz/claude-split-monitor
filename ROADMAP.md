# claude-split-monitor — Product Roadmap

## Vision

The developer dashboard you screenshot and share. Shows two Claude sessions working together in real-time — what each is doing, what it costs, how much faster you ship.

**The hook:** "I saved $1,200/month by splitting my Claude sessions instead of burning one context window."

---

## Phase 1: Core Dashboard (what exists)
Status: DONE

- Two agent panels (planner/executor)
- Pending/done task lists
- Message flow log
- WebSocket live updates
- Type badges + priority flags

---

## Phase 2: Analytics Strip
**Owner:** Desktop instance (dashboard.html)

Add a KPI strip across the top — 4 metrics that update live:

```
┌──────────┬──────────┬──────────┬──────────┐
│ Messages │  Pending │   Done   │  Status  │
│    12    │    3     │    9     │  ACTIVE  │
└──────────┴──────────┴──────────┴──────────┘
```

Tasks:
- [ ] D2.1: KPI strip component — 4 cards: total messages, pending, done, status
- [ ] D2.2: Message rate sparkline — tiny bar chart showing message frequency over time
- [ ] D2.3: Agent workload balance — visual bar showing % of tasks per agent
- [ ] D2.4: Last updated timestamp + uptime counter in header

---

## Phase 3: Session Intelligence
**Owner:** Terminal instance (server.py)

Make the server aware of actual Claude sessions, not just inbox files:

Tasks:
- [ ] S3.1: Session alive detection — scan ~/.claude/sessions/*.json for active PIDs, add planner_alive/executor_alive to payload
- [ ] S3.2: Token tracking — read session JSONL files for token counts (tokens_in, tokens_out per agent)
- [ ] S3.3: Cost estimation — calculate spend per agent based on token counts + model pricing
- [ ] S3.4: /api/health endpoint — {ok, split_dir, uptime, sessions_alive}
- [ ] S3.5: Activity timeline — last 60s of events per agent (tool calls, edits, thinking)

---

## Phase 4: Rich Visualizations
**Owner:** Desktop instance (dashboard.html)

Turn the data from Phase 3 into visuals people screenshot:

Tasks:
- [ ] D4.1: Token burn rate — live counter per agent, styled like a stock ticker
- [ ] D4.2: Cost tracker — "$X.XX spent this session" per agent + total, updates live
- [ ] D4.3: Agent activity timeline — horizontal bar per agent showing idle/thinking/coding/tool states over time
- [ ] D4.4: Task distribution donut chart — visual split of who did what
- [ ] D4.5: "Savings" banner — estimated cost of doing this sequentially vs parallel (the viral metric)

---

## Phase 5: Session History & Persistence
**Owner:** Terminal instance (server.py)

Tasks:
- [ ] S5.1: Session recording — save each cowork session state to ~/.claude-split/history/{timestamp}.json
- [ ] S5.2: Historical comparison — "this session vs last session" metrics
- [ ] S5.3: Aggregate stats — total tasks completed, total tokens, total cost across all sessions
- [ ] S5.4: /api/history endpoint — list past sessions with summary stats

---

## Phase 6: Polish & Ship
**Owner:** Both

Tasks:
- [ ] B6.1: Responsive layout — works on laptop, wide monitor, tablet
- [ ] B6.2: Dark/light theme toggle
- [ ] B6.3: Keyboard shortcuts — R to refresh, F for fullscreen, 1/2 to focus agent
- [ ] B6.4: Export — download session report as markdown or PNG screenshot
- [ ] B6.5: One-line install: `pip install claude-split-monitor && claude-split-monitor`
- [ ] B6.6: README with screenshots, GIF demo, badges

---

## Cowork Execution Plan

### Split:
- **Terminal (server.py):** Phases 3, 5, server parts of 6
- **Desktop (dashboard.html):** Phases 2, 4, UI parts of 6
- **Zero overlap:** server never touches HTML, dashboard never touches Python

### Execution order:
```
Phase 2 (Desktop) ──┐
                     ├── can run in parallel
Phase 3 (Terminal) ──┘
         │
         ▼
Phase 4 (Desktop) ── depends on Phase 3 data
         │
Phase 5 (Terminal) ── independent
         │
         ▼
Phase 6 (Both) ── final polish
```

### Contract:
Server broadcasts this shape (Phase 3 additions in bold):

```json
{
  "type": "cowork_state",
  "status": "active",
  "planner": {
    "pending": [...],
    "done": [...],
    "alive": true,
    "tokens_in": 45000,
    "tokens_out": 12000,
    "cost_usd": 0.42,
    "activity": ["tool_call", "edit", "thinking", ...]
  },
  "executor": { ... same shape ... },
  "flow": [...],
  "totals": {
    "messages": 12,
    "pending": 3,
    "done": 9,
    "total_cost": 0.87,
    "uptime_s": 3600,
    "sequential_estimate": 1.74
  }
}
```

Dashboard renders whatever fields exist — gracefully ignores missing ones so phases can ship independently.
