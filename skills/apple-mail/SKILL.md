---
name: apple-mail
description: Use only for Apple Mail or Mail.app tasks on macOS, including listing accounts and mailboxes, inspecting or searching messages, and reading, marking, archiving, moving, or deleting mail. Do not use for other Apple native apps, webmail, IMAP-only work, or generic macOS automation.
---

# Apple Mail

## Overview

This skill is the macOS Mail.app entry point. It implements `mail.*` automation
with JSON output designed for agent workflows.

## When to Use

- User asks to manage Apple Mail on this Mac
- User wants to inspect inboxes, triage messages, archive clutter, or move mail between folders
- User specifically wants local Mail.app behavior, not Gmail web UI or IMAP libraries

Do not use this skill for webmail sites opened in a browser.

## Command Surface

The helper lives next to this skill at `scripts/apple_apps.py`.

Read-only commands:

```bash
python3 scripts/apple_apps.py mail accounts
python3 scripts/apple_apps.py mail mailboxes --account "iCloud"
python3 scripts/apple_apps.py mail recent --account "SYSU" --limit 1 --include-read
python3 scripts/apple_apps.py mail triage-meta --account "SYSU" --mailbox-path "INBOX" --limit 5 --include-read --on-date "2026-03-18"
python3 scripts/apple_apps.py mail search --account "SYSU" --query "invoice" --limit 20
python3 scripts/apple_apps.py mail search --account "SYSU" --query "Beta view" --limit 10 --include-read --include-body
python3 scripts/apple_apps.py mail read --id 141819 --account "SYSU" --mailbox-path "INBOX"
```

Mutation commands:

```bash
python3 scripts/apple_apps.py mail mark --id 141819 --account "SYSU" --mailbox-path "INBOX" --read true
python3 scripts/apple_apps.py mail move --id 141819 --account "SYSU" --mailbox-path "INBOX" --to-mailbox "Archive"
python3 scripts/apple_apps.py mail archive --id 141819 --account "SYSU" --mailbox-path "INBOX"
python3 scripts/apple_apps.py mail delete --id 141819 --account "SYSU" --mailbox-path "INBOX"
```

## Workflow

1. For daily inbox triage, start with `triage-meta`.
2. For point lookups and thread recovery, use `search`.
3. For one-message inspection, use `recent`.
4. Capture the returned `id`, `account`, and `mailboxPath`.
5. Pass those exact values into `read`, `mark`, `move`, `archive`, or `delete`.

## Current Limits

- The fastest path for daily message triage is `triage-meta`, which reads lightweight metadata from headers without loading message bodies.
- `search` now prefers lightweight thread-aware matching when `--include-body` is not set. It can use subject, sender, recipients, message ids, and reply-chain headers to return both direct hits and nearby thread context.
- `search --include-body` now uses a two-stage path: lightweight recall first, then body reads for only a small candidate set. This is much more practical for recent-thread recovery, but it is still not a full-mailbox text index.
- `recent` is still useful for quick one-message inspection, especially `recent --account ... --limit 1 --include-read`.
- `read`, `mark`, `move`, `archive`, and `delete` are verified for top-level mailbox paths such as `INBOX` and `Archive`.
- After `move` or `archive`, Mail may assign a new internal numeric `id`; refresh it with another `recent` or `read` before the next mutation.

## Safety Rules

- Default to read-only exploration first.
- Before destructive actions (`move`, `archive`, `delete`), identify the exact target messages from `recent` or `search`.
- Prefer `mailboxPath` over `mailbox` when a folder name could be ambiguous.
