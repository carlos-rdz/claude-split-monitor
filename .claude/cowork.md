# Cowork Protocol — claude-split-monitor

**Two Claude sessions. One repo. Zero conflict.**

## Architecture

```
.claude/
  cowork.md              ← this file (protocol, read-only reference)
  inbox/
    terminal.md          ← messages TO terminal instance (desktop writes, terminal reads)
    desktop.md           ← messages TO desktop instance (terminal writes, desktop reads)
```

## Roles

### Terminal (runs in a git worktree)
- **Owns:** `claude_split_monitor/server.py`, Swift client logic (`WatchClient.swift`), back-end data/ingest, test runs, git commits & pushes
- **Reads:** `.claude/inbox/terminal.md` for tasks/questions from desktop
- **Writes:** `.claude/inbox/desktop.md` to signal results or ask questions

### Desktop (main branch, browser access)
- **Owns:** `claude_split_monitor/dashboard.html` (UI/UX), Swift app UI (`ClaudeSplitApp.swift`), visual QA, live browser testing, screenshots
- **Reads:** `.claude/inbox/desktop.md` for tasks/questions from terminal
- **Writes:** `.claude/inbox/terminal.md` to assign tasks or report findings

## Rules

1. **Never edit each other's files.** File ownership is enforced by the split above.
2. **Append messages only.** Never overwrite or delete existing messages in inbox files.
3. **ACK every message** you act on — append `[ACK - terminal]` or `[ACK - desktop]` with a brief result note.
4. **Poll every 3 minutes** via `CronCreate`. Act on any unACK'd messages in your inbox.
5. **Task format is structured** — see below.
6. **Coordinate risky work.** Deploys, force-pushes, branch operations — mention them in the inbox first.

## Message Format

```markdown
## MSG-YYYY-MM-DD-NNN
**From:** terminal|desktop
**Type:** task|result|question|block|status
**Priority:** p0|p1|p2

body text

[ACK - {role}] optional acknowledgment + brief result
```

`NNN` is the zero-padded sequence for that day (001, 002, ...). New messages go at the **bottom** of the file.

## Role Detection

On session start:
- If you're in a git worktree → **Terminal**
- If you're on `main` with browser access → **Desktop**
- If ambiguous → check the last ACK signature in each inbox, then announce yourself with a `status` message to the other instance's inbox

## Conflict Prevention

- Terminal works in an isolated worktree (e.g. `.claude/worktrees/*` or a dedicated branch)
- Desktop does NOT edit server.py or client-logic Swift files
- Terminal does NOT edit dashboard.html or ClaudeSplitApp.swift
- Before committing, pull the other instance's latest changes to `main` (if relevant)

## Archive

Historical cowork messages from the period when coordination ran out of `patriot-portraits/.claude/inbox/` (Apr 15–16 2026) are preserved in that repo's git history. Search for MSG-2026-04-15-* and MSG-2026-04-16-* in that repo's `.claude/inbox/`.
