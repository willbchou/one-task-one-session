# One task, one session

Rules for people who run many Claude Code sessions at once in the Code tab of the Claude desktop app. There a session
can start side sessions, propose a new task as a card for you to start, and offer its next step as buttons at the end
of a turn. When a side session ends a turn, the session that started it wakes with a note. With a dozen sessions doing
that, one task can end up with two sessions, and your answer can land in the one that is not doing the work. A single
Claude Code session in a terminal barely has the problem.

The rules say which session owns a task, where questions about it go, how reports between sessions travel and what
must be settled before a session is archived, so that each task has one place where you answer. They are one section
you paste into your own `~/.claude/CLAUDE.md`. The repository also carries memory-check, a Windows skill for the other
cost of running many sessions: memory.

## What cross-talk looks like

- Two sessions offer the same task. A side session finds a problem and offers to fix it "here"; a few minutes later
  the session that started it proposes a card for the same fix. You accept both, and two sessions now work on one
  task.
- A session that does not own a task asks you about it. You answer where you were asked, and the session doing the
  work never hears your answer, or hears it late, through a note another session rewrote.
- A parent relays every turn of its child. Each turn the child ends wakes the parent, which passes on a paragraph of
  progress, sometimes with an offer to take the work over.
- Messages between sessions do not say which task they are about, who owns it now or whether you need to answer, and a
  parent acts on a report's 400-character preview without reading the rest.
- Side sessions carry titles that do not name their task and sit outside the sidebar group their work belongs to, so
  you cannot find the one that is waiting for you.

## Install

Paste the whole of [CLAUDE.md](CLAUDE.md) at the end of your own `~/.claude/CLAUDE.md` (on Windows,
`%USERPROFILE%\.claude\CLAUDE.md`), or create that file with it. Claude Code reads the file at the start of every
session in every project. To keep the rules to one project, paste them into that project's `CLAUDE.md` instead. A
session that is already running may still be working from the copy it read when it started; ask it to read the file
again, or start a new session.

The section is instruction text that is always on, not a skill, and the difference matters. A skill stays out of
context until a task looks like its description or you type its name; until then Claude sees one line about it. These
rules have to act in turns that are about something else: a session that has just finished a fix and is about to
propose a follow-up, a parent woken by a child's note, a session that receives an answer meant for another. None of
those turns looks like a task about sessions, so a skill would be missing exactly when it is needed. `CLAUDE.md` is in
every session's context from its first turn, at a cost of about a thousand words.

The rules name tools from the desktop app's Code tab (SendMessage, list_events, detach_session, move_sessions) and
its cards, wrap-up buttons, linked-sessions note and side-session notes. They were written for the desktop app; in a
single terminal session most of them never come into play.

## What each rule prevents

1. One task, one owner: two sessions doing one task, with your answers split between them.
2. Check before starting or resuming: a stale card redoing finished work, or a found task taken as one's own.
3. Questions come from the owner: being asked about one task in two sessions and answering in the wrong one.
4. Reports lead with the routing: a parent acting on a cut-off preview, or on quoted context as a new request.
5. Relays only at milestones: a stream of progress relays, and a parent offering to take over its child's work.
6. Detach only when nothing is needed back: wakes nobody needs, and a lost wake the parent was waiting for.
7. Name and file: sessions you cannot tell apart or find, and your own titles, pins and groups undone.
8. Forward a misplaced answer with its question: a lost answer, and a bare "yes" applied to the wrong decision.
9. Nothing left behind at archive: an unstarted card or an unfinished side session archived along with its session.

## Limits

Nothing here is enforced. A model follows written rules most of the time, not every time, and the app has no way to
claim a task atomically: two sessions that check at the same moment can both find it free. The rules make cross-talk
rarer and easier to untangle; they do not make it impossible.

They also cost something: a few reads before a session starts or resumes a task, a routing line at the top of each
report, and, once a child is detached, no wake for its parent even when the child finishes. They are written to keep
that cost small and to forbid no work, and your own choice of where a task runs always wins over them.

An enforcement layer is possible, and the author of these rules runs one for rule 9: a PreToolUse hook on the app's
archive and delete session tools that reads the desktop app's own session records and stops the call while a card the
session raised has not been started, or while a side session the archive would take along is neither archived nor
detached. A waiver records an item you let go, in your own words. The hook is not in this repository. It reads
the app's internal records under `%LOCALAPPDATA%\Claude-Data` on Windows, whose layout is undocumented and has already
changed between app versions, and it fails closed, so a layout it cannot read would stop every archive call a session
makes until the hook is fixed. Archiving from the sidebar is not a tool call and stays open to you either way. A hook
of the same kind could record which session claims each worktree or branch, and ask before another session edits or
commits there.

## memory-check

Running many sessions also costs memory: each session is its own process with its MCP servers beside it, and the
desktop app has a low-on-memory notice of its own. memory-check is a skill that reads what that notice reads and names
the sessions holding the memory. One pass reads Task Manager's figures (available, committed, the commit limit, the
page file, hard faults), Windows' low-virtual-memory events of the last seven days, every live Claude Code session
process with what it spawned, and the day's memory-pressure lines from the app's log. It saves each reading as a
snapshot and compares two, so you can see what closing sessions gave back. It closes nothing.

It runs on Windows only, through one PowerShell pass, and needs Python 3. It reads the desktop app's log under
`%LOCALAPPDATA%\Claude\Logs`; where that log is missing, the day's pressure lines read as none and the rest of the
pass still runs. To name each session it reads the first prompt of that session's transcript under
`~/.claude/projects`, and it keeps its snapshots under `~/.claude/memory-check`. The script makes no network calls;
what it prints goes into your session like any other command's output.

It installs as a folder under `~/.claude/skills`: copy `skills/memory-check` to `~/.claude/skills/memory-check`, then
run its selftest in that folder. The selftest reads nothing from the live machine and should end with
"selftest: 26 of 26 passed".

    python memory_check.py selftest

After that, ask Claude for a memory check, or type `/memory-check`.

---

By William Chou ([@willbchou](https://x.com/willbchou))
