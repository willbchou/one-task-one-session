---
name: memory-check
description: The memory check for a Windows PC running many Claude desktop app sessions - one PowerShell pass reads what Task Manager's Performance tab shows (total, available, committed, the commit limit, the page file, hard faults), Windows' low-virtual-memory events of the last seven days, every live Claude Code session process with what it spawned, and the other processes holding the most commit; adds the app governor's pressure lines of the day from its main log; names each session process by its transcript; saves a snapshot; and compares two snapshots. Use when the app or Windows warns of low memory, when sessions slow down or a git, Node or ffmpeg step dies with "malloc failed", "spawn ENOMEM", exit 134 or a heap error, before a heavy job (an encode, a test suite, a batch) beside many sessions, when asked which sessions hold memory or are idle, or to see what closing sessions gave back. Subcommands - status [--no-save] [--no-events], compare [<a.json>] [<b.json>], snapshots, selftest; no argument runs status.
---

# Memory check: what the low-on-memory notice reads, and who holds the memory

The Claude desktop app has a low-on-memory notice of its own. Its CliGovernor polls every ten seconds and takes the
lower of available RAM over total RAM and commit available over the commit limit; below 5 percent is a warning, below
2 percent critical. Those are Task Manager's "Available" and "Committed x / y" lines, not "In use" and not the
per-process Memory column. Under pressure it evicts idle sessions; the cap on live sessions is max(6, RAM / 3 GiB),
and a session with Remote Control on is exempt from eviction while the live count is over the cap. These figures were
read from the app's bundle, and a later version of the app may change them. Windows has its own notice too, Event 2004
in the System log.

## The order

1. `python ~/.claude/skills/memory-check/memory_check.py status` (about ten seconds; `--no-events` skips the Windows
   event log and halves it). It prints the system line, the governor's reading now and its lines of the day, the
   Windows events, the session processes largest first and the other process names, then saves the snapshot under
   `~/.claude/memory-check/`.
2. Name the sessions. The `session` column is the first eight characters of the session id the process was resumed
   with, the app's own id (`local_<id>`), and the transcript's folder, last write and first prompt come with it. A
   session started from another (a fork, a side session) has no own id on its command line: the column reads
   `by <id>`, the starter's id from the first side-session-notes folder it was given, and the title names the project
   root. Call `list_sessions` and join: own ids on `sessionId`, starters on `startedBy`, two sessions with the same
   starter told apart by the process's start time against the list and by their `cwd`. `-` with no transcript is a
   session the app started fresh (a new session, a scheduled task). `isRunning` from the list is the working state;
   the process's `last` is when its transcript was last written.
3. Say what holds the memory: the `kids` column names what a session spawned (a wrangler dev server as `workerdx15`, a
   browser it drives as `chromex8`, a batch as `pythonx9`), which is usually where the big numbers are, and `others`
   names the rest of the machine (browsers, other apps, node, python). Pinned sessions, and any the user has marked as
   ones to keep, are the user's alone: list them, never archive or close them. The skill closes nothing; a session
   paused by the governor resumes when touched.
4. After sessions are closed or a job ends, `status` again and `compare` (the two latest snapshots, or two named
   files): the system figures, then every process by pid with before, now and change, `gone` and `new` marked.

## Reading it

- `available` under 5 percent of RAM is the governor's warning (0.8 GB on 16 GB), under 2 percent critical (0.3 GB).
  `committed` near the commit limit is where allocations fail: git's "malloc failed" (WinError 1455, the paging file
  too small), Node's "spawn ENOMEM", a Node process aborting exit 134 "JavaScript heap out of memory", Python's
  MemoryError. Those are memory casualties: rerun, never debug the code for them.
- `hard faults` above a few thousand pages a second means the disk is doing memory's work; the machine is slow for
  every session, not only the one that asked.
- Each session process, with the MCP servers it starts, commits about 600 MB, about 100 MB resident; more servers mean
  more. Twenty idle sessions are 12 GB of commit. The fixes, in order: one heavy job at a time (an encode, a
  transcription, a test suite, a batch), fewer warm sessions, Remote Control off on sessions the user does not open
  from a phone (a session with Remote Control on is never evicted while the live count is over the cap; the default
  for new sessions is in the app's settings), a fixed-size page file (initial = maximum, so it never grows
  mid-allocation; the user's to set in System > Advanced > Performance > Virtual memory), and more RAM.
- The app's main log is `%LOCALAPPDATA%\Claude\Logs\main*.log` (`[CliGovernor]` lines; `main1.log` is the first
  rotation).

## Checks

`python memory_check.py selftest` builds a throwaway folder with a governor log, a transcript and two snapshots and
runs the parser, the naming, the status and compare renderers and the snapshot store against them, then asks
PowerShell whether the pass parses (skipped where there is no PowerShell): 26 checks in about three seconds, nothing
read from the live machine.
