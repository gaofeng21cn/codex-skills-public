#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CLI="$BASE_DIR/scripts/apple_apps.py"

accounts_json="$(python3 "$CLI" mail accounts)"
first_account="$(
  python3 - "$accounts_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, list) and data, "accounts must be a non-empty list"
print(data[0]["name"])
PY
)"

mailboxes_json="$(python3 "$CLI" mail mailboxes --account "$first_account")"
python3 - "$mailboxes_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, list), "mailboxes must be a list"
assert data, "mailboxes must not be empty"
assert "name" in data[0], "mailbox item must include name"
PY

recent_json="$(python3 "$CLI" mail recent --account "$first_account" --limit 1 --include-read)"
python3 - "$recent_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, list), "recent must be a list"
PY

triage_json="$(python3 "$CLI" mail triage-meta --account "$first_account" --mailbox-path INBOX --limit 1 --include-read)"
python3 - "$triage_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, list), "triage-meta must be a list"
if data:
    item = data[0]
    assert "headerDate" in item, "triage-meta item must include headerDate"
    assert "headerDateIso" in item, "triage-meta item must include headerDateIso"
PY

search_json="$(python3 "$CLI" mail search --account "$first_account" --query "$first_account" --limit 3 --include-read)"
python3 - "$search_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, list), "search must be a list"
if data:
    item = data[0]
    assert "matchType" in item, "search item must include matchType"
PY

search_body_json="$(python3 "$CLI" mail search --account "$first_account" --query "$first_account" --limit 3 --include-read --include-body)"
python3 - "$search_body_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, list), "search --include-body must be a list"
PY

msg_fields="$(
  python3 - "$recent_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
if not data:
    print("\t\t\t")
else:
    msg = data[0]
    print(
        f"{msg.get('id','')}\t{msg.get('account','')}\t{msg.get('mailbox','')}\t"
        f"{'true' if msg.get('read') else 'false'}"
    )
PY
)"

msg_id="$(printf '%s' "$msg_fields" | cut -f1)"
msg_account="$(printf '%s' "$msg_fields" | cut -f2)"
msg_mailbox="$(printf '%s' "$msg_fields" | cut -f3)"
msg_read="$(printf '%s' "$msg_fields" | cut -f4)"

if [ -n "$msg_id" ] && [ -n "$msg_account" ] && [ -n "$msg_mailbox" ]; then
  read_json="$(python3 "$CLI" mail read --id "$msg_id" --account "$msg_account" --mailbox "$msg_mailbox")"
  python3 - "$read_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, dict), "read must return an object"
assert "subject" in data, "read result must include subject"
assert "content" in data, "read result must include content"
PY

  mark_json="$(python3 "$CLI" mail mark --id "$msg_id" --account "$msg_account" --mailbox "$msg_mailbox" --read "$msg_read")"
  python3 - "$mark_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
assert isinstance(data, dict), "mark must return an object"
assert data.get("ok") is True, "mark must return ok=true"
PY
fi

printf 'smoke ok\n'
