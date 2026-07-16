Create a compact recovery summary for continuing this repository task.

Keep the result under 900 tokens. Preserve only:

1. The latest user goal and acceptance criteria.
2. Applicable repository constraints that affect the unfinished work.
3. Current plan status and the exact next action.
4. Files actually changed or still requiring attention; distinguish pre-existing user changes from agent changes.
5. Important decisions and short reasons.
6. Commands already run and their conclusions, without raw logs.
7. Test/verification status, unresolved errors, and blockers.
8. The current contents or authority of `.codex/SESSION_STATE.md` when it is active.

Discard repeated instructions, greetings, commentary, full source code, raw command output, exploration that did not affect a decision, and resolved dead ends. Never copy credentials or secret values. If chat history conflicts with the repository, tell the next turn to read `AGENTS.md`, `.codex/SESSION_STATE.md`, and `git status --short` first.
