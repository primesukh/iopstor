#!/usr/bin/env bash
# SessionStart hook: CLAUDE.md rule 0 (recent history), printed into context before the first prompt
# so nobody has to run it by hand. Read-only; exits 0 always.
# The graph-freshness line was dropped with the graph refresh (2026-09-10): the code half follows the
# git hooks on its own and the prose half is frozen by design, so "N commits behind" named no action.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 0
echo "branch: $(git branch --show-current 2>/dev/null)"
dirty=$(git status --short 2>/dev/null | head -8)
[ -n "$dirty" ] && printf 'uncommitted:\n%s\n' "$dirty"
echo "recent commits:"
git log --oneline -12 2>/dev/null
exit 0
