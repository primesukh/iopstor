#!/usr/bin/env bash
# SessionStart hook: CLAUDE.md rule 0 (recent history) and the graph-freshness check, printed into
# context before the first prompt so nobody has to run them by hand. Read-only; exits 0 always.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 0
echo "branch: $(git branch --show-current 2>/dev/null)"
dirty=$(git status --short 2>/dev/null | head -8)
[ -n "$dirty" ] && printf 'uncommitted:\n%s\n' "$dirty"
echo "recent commits:"
git log --oneline -12 2>/dev/null
built=$(sed -n 's/^- Built from commit: `\([0-9a-f]*\)`.*/\1/p' graphify-out/GRAPH_REPORT.md 2>/dev/null)
if [ -n "$built" ]; then
  behind=$(git rev-list --count "$built..HEAD" 2>/dev/null || echo '?')
  echo "graphify graph: built from $built, $behind commit(s) behind HEAD (git hooks rebuild code per commit; if this is not 0 see ~/.cache/graphify-rebuild.log; prose + labels refresh on main via /after-merge)"
else
  echo "graphify graph: not built (graphify-out/GRAPH_REPORT.md missing)"
fi
exit 0
