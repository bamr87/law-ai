#!/usr/bin/env bash
# PostToolUse hook (Write|Edit) — after an edit to BACKLOG.md or anything under
# specs/, run the two stdlib gates (spec_validator + backlog_lint) and, if they
# fail, feed the failure back so the model fixes it before moving on. These are
# the constitution §11 gates and are the only sanctioned host-run Python checks.
set +e

payload="$(cat)"
f="$(printf '%s' "$payload" | python3 -c 'import json,sys;d=json.load(sys.stdin);ti=d.get("tool_input") or {};tr=d.get("tool_response") or {};print(ti.get("file_path") or tr.get("filePath") or "")' 2>/dev/null)"

# PostToolUse fires only on successful Write/Edit calls, whose file_path is
# always absolute — no relative-path case needed.
case "$f" in
  *BACKLOG.md | */specs/*) ;;
  *) exit 0 ;;
esac

# Locate repo root (hook cwd is normally the project root, but be defensive).
root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
sv_out="$(cd "$root" && python3 scripts/spec_validator.py 2>&1)"; sv=$?
bl_out="$(cd "$root" && python3 scripts/backlog_lint.py 2>&1)"; bl=$?
out="$(printf '%s\n---\n%s' "$sv_out" "$bl_out")"

if [ "$sv" -ne 0 ] || [ "$bl" -ne 0 ]; then
  python3 - "$out" <<'PY' 2>/dev/null || printf '{}'
import json, sys
msg = "Spec/backlog gate failed after your edit (fix before continuing):\n" + sys.argv[1][:2500]
print(json.dumps({"decision": "block", "reason": msg}))
PY
fi
exit 0
