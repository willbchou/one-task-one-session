## One task, one session: where questions and reports go

When many Claude Code sessions run at once in the Claude desktop app, sessions start side sessions, propose cards and
wake each other. One task can then end up with two sessions, the user can be asked about it in both, and an answer
given in one can miss the session doing the work. So, in every session:

1. One task, one owner. A task's owner is the session that first offered it to the user or was given it, by the user,
   by a brief or by a scheduled run (each run its own owner). Ownership survives compaction, a pause, an account
   switch and a usage limit; a fork, a review, a variant or a delegated subtask owns only the scope its brief names. A
   follow-up the owner's work turns up stays with the owner unless the user sends it elsewhere or the owner hands it
   to a new session with a brief. Each scope gets one offer or one card, never both: a session that proposes a card
   first checks that no linked session has offered or taken the work (its last wrap-up, read with list_events). The
   user's own choice to run a task in two sessions on purpose (a second opinion, a variant) stands.

   It prevents two sessions doing one task, with the user's answers split between them.

2. Check before starting or resuming, from a card or a wrap-up button included, since both outlive the work they
   offered. Read the memory notes on the task, the linked-sessions note, the side-session notes and the branch or
   worktree state. A session the app does not list, such as another coding agent's, has no app record, so a memory
   note naming it is the record, and no record means unknown, not free. Work already done is said in one line and
   left; a task another session owns goes back to that owner by message; a conflicting claim or a takeover is settled
   with the owner, or with the user when the owner cannot answer, before the task counts as moved, and the handoff
   (scope, state, branch) goes in a memory note on the task. Standing down throws no finding away.

   It prevents a stale card or button from redoing finished work, and finding a task from counting as owning it.

3. A task's questions come from its owner. A session with a question about another session's task sends it to the
   owner (SendMessage), not to the user. The user's own questions and answers are handled where the user puts them: a
   session that is not the owner names the task, the owner and the pending question, takes the user's answer, and
   relays it under rule 8; ownership does not move with it.

   It prevents the user being asked about one task in two sessions and answering in the one not doing the work.

4. A report or a forwarded note starts with the task, its source, its current owner and whether anything is the user's
   to answer, here or in the owner's session, inside its first 400 characters, since a parent sees only those at
   first. The parent reads the whole report before acting on the preview and tells quoted context from a fresh
   request. Most say "nothing to answer".

   It prevents a parent acting on a cut-off preview, and quoted context being taken for a new request.

5. Relays only at milestones. A parent passes on a child's note once, with the child's link, when the child needs the
   user, lands, blocks or finishes, and folds routine progress into the next milestone. A note that is none of these
   gets one line at most, no question, and never an offer to take the child's work over. Being asked to monitor a
   child means that.

   It prevents a stream of progress relays, and a parent offering to take over work its child is doing.

6. "No need to report back" from the user allows detaching the child (detach_session) once its brief is
   self-contained and the parent needs nothing back, said once to the user: detaching stops every later wake of the
   parent, completion and blockers included, and ends their joint archiving. A child the parent depends on stays
   attached, under rule 5.

   It prevents wakes nobody needs, and the lost wake of a child whose result or blocker the parent still needed.

7. Name and file. A new session's title names its task and scope in a few words. A title the user set, a pin and a
   filing the user chose are never changed. A session that starts another files it in an existing sidebar group that
   plainly belongs to the task (move_sessions); takeover provenance goes in the brief, not the title.

   It prevents sessions the user cannot tell apart or find, and a session undoing the user's titles, pins or groups.

8. An answer that lands in the wrong session is forwarded to the confirmed owner with the user's exact words, the
   original question or button and the session it came from; an ambiguous reply ("yes", "do it here") is clarified
   with the user before it goes. The owner applies it to that decision only after checking the scope is still
   current; the forwarder says whether it was sent, acknowledged or could not be delivered; a shared note updated on
   the way is a record, never proof of receipt.

   It prevents a lost answer, and a bare "yes" applied to the wrong decision or to one already superseded.

9. Nothing left behind at archive. A session is archived only when each of its requests is done and checked, handed
   to a session the user has started, or let go in the user's own words. A card it raised that nobody has started, and
   a side session the archive would take with it, are pending: the session waits, or the user starts the card, or the
   child is detached first.

   It prevents an archive that takes unfinished work with it: a card nobody started, or a side session not yet done.

These are the defaults for where a task's questions and reports go. They cost a few reads per check and never narrow
what a session may do; the user's explicit choice of a session or of parallel work wins over them, and the user's
other rules, such as those on worktrees, reviews or shared data, stand beside them.
