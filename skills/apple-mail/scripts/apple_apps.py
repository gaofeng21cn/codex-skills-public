#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
MAIL_SCRIPT = SCRIPT_DIR / "apple_apps_mail.js"
RECENT_SCRIPT = SCRIPT_DIR / "recent_mail.applescript"
KEY_MAP = {
    "mailbox_path": "mailboxPath",
    "message_id": "messageId",
    "include_read": "includeRead",
    "include_body": "includeBody",
    "on_date": "onDate",
    "max_scan_per_box": "maxScanPerBox",
    "to_account": "toAccount",
    "to_mailbox": "toMailbox",
    "to_mailbox_path": "toMailboxPath",
    "archive_mailbox": "archiveMailbox",
    "archive_mailbox_path": "archiveMailboxPath",
}
FAST_INBOX_NAMES = {"INBOX", "Inbox", "收件箱", "收件匣"}
FAST_ACCOUNT_NAMES_SCRIPT = 'tell application "Mail" to get name of every account'
HEADER_NAME_MAP = {
    "subject": {"subject", "主题"},
    "sender": {"from", "发件人"},
    "date": {"date", "日期"},
    "to": {"to", "收件人"},
    "message_id": {"message-id"},
    "in_reply_to": {"in-reply-to"},
    "references": {"references"},
}
MESSAGE_ID_PATTERN = re.compile(r"<[^>]+>")
THREAD_PREFIX_PATTERN = re.compile(r"^\s*(?:(?:re|fw|fwd)(?:\[\d+\])?:\s*)+", re.IGNORECASE)


def str_to_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def unfold_headers(headers: str) -> list[tuple[str, str]]:
    unfolded: list[tuple[str, str]] = []
    current_name: str | None = None
    current_value: list[str] = []
    for raw_line in headers.splitlines():
        if raw_line[:1] in {" ", "\t"} and current_name is not None:
            current_value.append(raw_line.strip())
            continue
        if current_name is not None:
            unfolded.append((current_name, " ".join(current_value).strip()))
        if ":" not in raw_line:
            current_name = None
            current_value = []
            continue
        name, value = raw_line.split(":", 1)
        current_name = name.strip()
        current_value = [value.strip()]
    if current_name is not None:
        unfolded.append((current_name, " ".join(current_value).strip()))
    return unfolded


def extract_header_value(headers: str, logical_name: str) -> tuple[str | None, str | None]:
    wanted = HEADER_NAME_MAP[logical_name]
    for name, value in unfold_headers(headers):
        if name.strip().lower() in wanted:
            return name, value
    return None, None


def parse_header_datetime(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    zh_match = re.match(
        r"^(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日\s+GMT(?P<offset>[+-]\d{1,2})(?::?(?P<offset_minutes>\d{2}))?\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?$",
        cleaned,
    )
    if zh_match:
        offset_hours = int(zh_match.group("offset"))
        offset_minutes = int(zh_match.group("offset_minutes") or 0)
        offset_delta = timedelta(hours=abs(offset_hours), minutes=offset_minutes)
        if offset_hours < 0:
            offset_delta = -offset_delta
        dt = datetime(
            int(zh_match.group("year")),
            int(zh_match.group("month")),
            int(zh_match.group("day")),
            int(zh_match.group("hour")),
            int(zh_match.group("minute")),
            int(zh_match.group("second") or 0),
            tzinfo=timezone(offset_delta),
        )
        return dt.isoformat()
    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.isoformat()
    return parsed.isoformat()


def extract_received_date(headers: str) -> tuple[str | None, str | None]:
    for name, value in unfold_headers(headers):
        if name.strip().lower() != "received":
            continue
        _, separator, date_value = value.rpartition(";")
        candidate = date_value.strip() if separator else value.strip()
        parsed = parse_header_datetime(candidate)
        if parsed:
            return candidate, parsed
    return None, None


def extract_header_metadata(headers: str) -> dict[str, str | None]:
    subject_name, subject_value = extract_header_value(headers, "subject")
    sender_name, sender_value = extract_header_value(headers, "sender")
    date_name, date_value = extract_header_value(headers, "date")
    date_iso = parse_header_datetime(date_value)
    date_source = date_name
    if not date_iso:
        date_value, date_iso = extract_received_date(headers)
        if date_iso:
            date_source = "Received"
    return {
        "subject": subject_value,
        "sender": sender_value,
        "headerDate": date_value,
        "headerDateIso": date_iso,
        "dateSource": date_source,
    }


def normalize_thread_subject(subject: str | None) -> str:
    if not subject:
        return ""
    normalized = " ".join(subject.split()).strip()
    previous = None
    while previous != normalized:
        previous = normalized
        normalized = THREAD_PREFIX_PATTERN.sub("", normalized).strip()
    return normalized.lower()


def parse_message_id_list(value: str | None) -> list[str]:
    if not value:
        return []
    return MESSAGE_ID_PATTERN.findall(value)


def canonicalize_message_id(value: str | None) -> str | None:
    if not value:
        return None
    ids = parse_message_id_list(value)
    if ids:
        return ids[0]
    cleaned = value.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("<"):
        cleaned = f"<{cleaned}"
    if not cleaned.endswith(">"):
        cleaned = f"{cleaned}>"
    return cleaned


def extract_thread_metadata(row: dict, headers: str) -> dict[str, object]:
    _, subject_value = extract_header_value(headers, "subject")
    _, to_value = extract_header_value(headers, "to")
    _, message_id_value = extract_header_value(headers, "message_id")
    _, in_reply_to_value = extract_header_value(headers, "in_reply_to")
    _, references_value = extract_header_value(headers, "references")
    subject = subject_value or str(row.get("subject") or "")
    return {
        "messageId": canonicalize_message_id(message_id_value or str(row.get("messageId") or "")),
        "inReplyTo": canonicalize_message_id(in_reply_to_value),
        "references": parse_message_id_list(references_value),
        "subjectBase": normalize_thread_subject(subject),
        "to": to_value,
    }


def build_triage_meta_item(row: dict, headers: str) -> dict:
    metadata = extract_header_metadata(headers)
    return {
        "id": row.get("id"),
        "messageId": row.get("messageId"),
        "subject": metadata.get("subject") or row.get("subject"),
        "sender": metadata.get("sender") or row.get("sender"),
        "read": row.get("read"),
        "mailbox": row.get("mailbox"),
        "mailboxPath": row.get("mailboxPath"),
        "account": row.get("account"),
        "headerDate": metadata.get("headerDate"),
        "headerDateIso": metadata.get("headerDateIso"),
        "dateSource": metadata.get("dateSource"),
    }


def build_search_meta_item(row: dict, headers: str) -> dict:
    item = build_triage_meta_item(row, headers)
    item.update(extract_thread_metadata(row, headers))
    return item


def filter_triage_items(items: list[dict], *, on_date: str | None, include_read: bool) -> list[dict]:
    filtered: list[dict] = []
    for item in items:
        if not include_read and item.get("read"):
            continue
        header_date_iso = str(item.get("headerDateIso") or "")
        if on_date and not header_date_iso.startswith(on_date):
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: item.get("headerDateIso") or "", reverse=True)
    return filtered


def build_searchable_text(item: dict) -> str:
    parts = [
        str(item.get("subject") or ""),
        str(item.get("subjectBase") or ""),
        str(item.get("sender") or ""),
        str(item.get("to") or ""),
        str(item.get("messageId") or ""),
        str(item.get("inReplyTo") or ""),
        " ".join(str(value) for value in item.get("references") or []),
    ]
    return "\n".join(parts).lower()


def score_search_item(item: dict, query: str) -> int:
    if not query:
        return 0
    subject = str(item.get("subject") or "").lower()
    subject_base = str(item.get("subjectBase") or "").lower()
    sender = str(item.get("sender") or "").lower()
    recipient = str(item.get("to") or "").lower()
    message_id = str(item.get("messageId") or "").lower()
    in_reply_to = str(item.get("inReplyTo") or "").lower()
    references = " ".join(str(value).lower() for value in item.get("references") or [])
    searchable = build_searchable_text(item)

    score = 0
    if query in message_id or query in in_reply_to or query in references:
        score += 120
    if query in subject:
        score += 90
    if query in subject_base:
        score += 70
    if query in sender:
        score += 80
    if query in recipient:
        score += 60
    if item.get("bodyHit"):
        score += 85
    if score == 0 and query in searchable:
        score += 40
    return score


def search_meta_items(items: list[dict], *, query: str, limit: int) -> list[dict]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return sorted(items, key=lambda item: item.get("headerDateIso") or "", reverse=True)[:limit]

    direct_matches: list[dict] = []
    thread_subjects: set[str] = set()
    thread_ids: set[str] = set()

    for item in items:
        score = score_search_item(item, normalized_query)
        if score <= 0:
            continue
        direct_item = dict(item)
        direct_item["matchType"] = "direct"
        direct_item["matchScore"] = score
        direct_matches.append(direct_item)
        subject_base = str(item.get("subjectBase") or "")
        if subject_base:
            thread_subjects.add(subject_base)
        for value in [item.get("messageId"), item.get("inReplyTo"), *(item.get("references") or [])]:
            if value:
                thread_ids.add(str(value))

    direct_matches.sort(key=lambda item: (item.get("matchScore") or 0, item.get("headerDateIso") or ""), reverse=True)
    if not direct_matches:
        return []

    direct_ids = {item.get("id") for item in direct_matches}
    context_matches: list[dict] = []
    for item in items:
        if item.get("id") in direct_ids:
            continue
        candidate_ids = {
            str(value)
            for value in [item.get("messageId"), item.get("inReplyTo"), *(item.get("references") or [])]
            if value
        }
        subject_base = str(item.get("subjectBase") or "")
        has_reply_chain = bool(item.get("inReplyTo") or item.get("references"))
        shares_thread = bool(candidate_ids & thread_ids)
        if not shares_thread and subject_base and subject_base in thread_subjects and has_reply_chain:
            shares_thread = True
        if not shares_thread:
            continue
        context_item = dict(item)
        context_item["matchType"] = "thread"
        context_item["matchScore"] = 0
        context_matches.append(context_item)

    context_matches.sort(key=lambda item: item.get("headerDateIso") or "", reverse=True)
    return (direct_matches + context_matches)[:limit]


def run_mail(action: str, payload: dict) -> object:
    cmd = [
        "osascript",
        "-l",
        "JavaScript",
        str(MAIL_SCRIPT),
        action,
        json.dumps(payload, ensure_ascii=False),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise SystemExit(message or f"mail command failed: {action}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON from Mail helper: {exc}") from exc


def run_applescript(script: str, args: list[str]) -> str:
    cmd = ["osascript", "-e", script, *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise SystemExit(message or "AppleScript command failed")
    return result.stdout.strip()


def run_applescript_file(path: Path, args: list[str]) -> str:
    cmd = ["osascript", str(path), *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise SystemExit(message or "AppleScript file command failed")
    return result.stdout.strip()


def parse_recent_rows_output(output: str) -> list[dict]:
    rows: list[dict] = []
    if not output:
        return rows
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 9:
            continue
        rows.append(
            {
                "id": int(parts[0]),
                "messageId": parts[1],
                "subject": parts[2],
                "sender": parts[3],
                "read": parts[4].strip().lower() == "true",
                "mailbox": parts[5],
                "mailboxPath": parts[5],
                "account": parts[6],
                "dateReceived": parts[7] or None,
                "dateSent": parts[8] or None,
            }
        )
    return rows


def run_jxa_inline(script: str, args: list[str]) -> object:
    cmd = ["osascript", "-l", "JavaScript", "-e", script, *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise SystemExit(message or "inline JXA command failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON from inline JXA helper: {exc}") from exc


def list_account_names_fast() -> list[str]:
    output = run_applescript(FAST_ACCOUNT_NAMES_SCRIPT, [])
    if not output:
        return []
    return [item.strip() for item in output.split(",") if item.strip()]


def can_use_fast_recent(payload: dict) -> bool:
    mailbox = payload.get("mailboxPath") or payload.get("mailbox")
    if not mailbox:
        return True
    return mailbox in FAST_INBOX_NAMES


def fast_recent(payload: dict) -> list[dict]:
    requested_limit = int(payload.get("limit", 20))
    mailbox_name = str(payload.get("mailboxPath") or payload.get("mailbox") or "INBOX")
    if payload.get("account") and requested_limit == 1 and mailbox_name in FAST_INBOX_NAMES:
        rows = inline_recent_for_account(str(payload["account"]), mailbox_name, 1)
        if payload.get("includeRead"):
            return rows[:1]
        filtered = [row for row in rows if not row.get("read")]
        return filtered[:1]

    if payload.get("account"):
        accounts = [str(payload["account"])]
    else:
        accounts = list_account_names_fast()

    per_account_limit = int(payload.get("maxScanPerBox") or max(requested_limit + 2, 5))
    include_read = bool(payload.get("includeRead"))
    rows: list[dict] = []

    for account_name in accounts:
        try:
            output = run_applescript_file(RECENT_SCRIPT, [account_name, mailbox_name, str(per_account_limit)])
        except SystemExit:
            continue
        for item in parse_recent_rows_output(output):
            if not include_read and item["read"]:
                continue
            rows.append(item)

    rows.sort(key=lambda item: item.get("dateReceived") or item.get("dateSent") or "", reverse=True)
    return rows[:requested_limit]


def can_use_inline_mailbox(payload: dict) -> bool:
    mailbox = str(payload.get("mailboxPath") or payload.get("mailbox") or "")
    return bool(payload.get("account")) and bool(mailbox) and "/" not in mailbox


def inline_recent_for_account(account: str, mailbox: str, limit: int) -> list[dict]:
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var account = app.accounts.byName(argv[0]);
  var box = account.mailboxes.byName(argv[1]);
  var limit = Number(argv[2]);
  var out = [];
  for (var i = 0; i < limit; i++) {
    var message = box.messages[i];
    if (!message) {
      break;
    }
    try {
      out.push({
        id: message.id(),
        messageId: message.messageId(),
        subject: message.subject(),
        sender: message.sender(),
        read: message.readStatus(),
        mailbox: box.name(),
        mailboxPath: box.name(),
        account: account.name()
      });
    } catch (error) {
      break;
    }
  }
  return JSON.stringify(out);
}
'''
    return run_jxa_inline(script, [account, mailbox, str(limit)])


def recent_rows_for_account(account: str, mailbox: str, limit: int) -> list[dict]:
    output = run_applescript_file(RECENT_SCRIPT, [account, mailbox, str(limit)])
    return parse_recent_rows_output(output)


def search_recent_rows_for_account(account: str, mailbox: str, limit: int, *, start_index: int = 1) -> list[dict]:
    script = r'''
on sanitizeText(valueText)
    set sourceText to valueText as text
    set oldTids to AppleScript's text item delimiters
    set AppleScript's text item delimiters to {return, linefeed, tab}
    set parts to text items of sourceText
    set AppleScript's text item delimiters to " "
    set cleanedText to parts as text
    set AppleScript's text item delimiters to oldTids
    return cleanedText
end sanitizeText

on run argv
    set accountName to item 1 of argv
    set mailboxName to item 2 of argv
    set requestedLimit to (item 3 of argv) as integer
    set startIndex to (item 4 of argv) as integer

    tell application "Mail"
        tell mailbox mailboxName of account accountName
            set totalCount to count of messages
            if totalCount is 0 then
                return ""
            end if
            if startIndex < 1 then
                set startIndex to 1
            end if
            if startIndex > totalCount then
                return ""
            end if
            set endIndex to (startIndex + requestedLimit - 1)
            if endIndex > totalCount then
                set endIndex to totalCount
            end if
            set messageIds to (get id of messages startIndex thru endIndex)
            set internetMessageIds to (get message id of messages startIndex thru endIndex)
            set subjects to (get subject of messages startIndex thru endIndex)
            set senders to (get sender of messages startIndex thru endIndex)
            set readStatuses to (get read status of messages startIndex thru endIndex)
            set rows to {}
            set rowCount to (endIndex - startIndex + 1)
            repeat with i from 1 to rowCount
                set end of rows to ((item i of messageIds as text) & tab & my sanitizeText(item i of internetMessageIds) & tab & my sanitizeText(item i of subjects) & tab & my sanitizeText(item i of senders) & tab & (item i of readStatuses as text) & tab & mailboxName & tab & accountName & tab & tab)
            end repeat
        end tell
    end tell

    set oldTids to AppleScript's text item delimiters
    set AppleScript's text item delimiters to linefeed
    set outputText to rows as text
    set AppleScript's text item delimiters to oldTids
    return outputText
end run
'''
    output = run_applescript(script, [account, mailbox, str(limit), str(start_index)])
    return parse_recent_rows_output(output)


def inline_read(payload: dict) -> dict:
    mailbox = str(payload.get("mailboxPath") or payload.get("mailbox"))
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var account = app.accounts.byName(argv[0]);
  var box = account.mailboxes.byName(argv[1]);
  var message = box.messages.byId(Number(argv[2]));
  return JSON.stringify({
    id: message.id(),
    messageId: message.messageId(),
    subject: message.subject(),
    sender: message.sender(),
    read: message.readStatus(),
    flagged: message.flaggedStatus(),
    mailbox: box.name(),
    mailboxPath: box.name(),
    account: account.name(),
    content: message.content(),
    allHeaders: message.allHeaders()
  });
}
'''
    return run_jxa_inline(script, [str(payload["account"]), mailbox, str(payload["id"])])


def inline_triage_meta_for_account(account: str, mailbox: str, limit: int) -> list[dict]:
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var account = app.accounts.byName(argv[0]);
  var box = account.mailboxes.byName(argv[1]);
  var limit = Number(argv[2]);
  var out = [];
  for (var i = 0; i < limit; i++) {
    var message = box.messages[i];
    if (!message) {
      break;
    }
    try {
      out.push({
        id: message.id(),
        messageId: message.messageId(),
        subject: message.subject(),
        sender: message.sender(),
        read: message.readStatus(),
        mailbox: box.name(),
        mailboxPath: box.name(),
        account: account.name(),
        allHeaders: message.allHeaders()
      });
    } catch (error) {
      break;
    }
  }
  return JSON.stringify(out);
}
'''
    return run_jxa_inline(script, [account, mailbox, str(limit)])


def inline_headers_for_messages(account: str, mailbox: str, message_ids: list[int]) -> list[dict]:
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var account = app.accounts.byName(argv[0]);
  var box = account.mailboxes.byName(argv[1]);
  var ids = JSON.parse(argv[2]);
  var out = [];
  for (var i = 0; i < ids.length; i++) {
    try {
      var message = box.messages.byId(Number(ids[i]));
      out.push({
        id: message.id(),
        allHeaders: message.allHeaders()
      });
    } catch (error) {
      continue;
    }
  }
  return JSON.stringify(out);
}
'''
    return run_jxa_inline(script, [account, mailbox, json.dumps(message_ids)])


def inline_bodies_for_messages(account: str, mailbox: str, message_ids: list[int]) -> list[dict]:
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var account = app.accounts.byName(argv[0]);
  var box = account.mailboxes.byName(argv[1]);
  var ids = JSON.parse(argv[2]);
  var out = [];
  for (var i = 0; i < ids.length; i++) {
    try {
      var message = box.messages.byId(Number(ids[i]));
      out.push({
        id: message.id(),
        content: message.content(),
        allHeaders: message.allHeaders()
      });
    } catch (error) {
      continue;
    }
  }
  return JSON.stringify(out);
}
'''
    return run_jxa_inline(script, [account, mailbox, json.dumps(message_ids)])


def inline_mark(payload: dict) -> dict:
    mailbox = str(payload.get("mailboxPath") or payload.get("mailbox"))
    read_value = "" if payload.get("read") is None else ("true" if payload.get("read") else "false")
    flagged_value = "" if payload.get("flagged") is None else ("true" if payload.get("flagged") else "false")
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var account = app.accounts.byName(argv[0]);
  var box = account.mailboxes.byName(argv[1]);
  var message = box.messages.byId(Number(argv[2]));
  if (argv[3] !== "") {
    message.readStatus = argv[3] === "true";
  }
  if (argv[4] !== "") {
    message.flaggedStatus = argv[4] === "true";
  }
  return JSON.stringify({
    ok: true,
    id: message.id(),
    account: account.name(),
    mailbox: box.name(),
    mailboxPath: box.name(),
    read: message.readStatus(),
    flagged: message.flaggedStatus()
  });
}
'''
    return run_jxa_inline(script, [str(payload["account"]), mailbox, str(payload["id"]), read_value, flagged_value])


def inline_move(payload: dict) -> dict:
    source_mailbox = str(payload.get("mailboxPath") or payload.get("mailbox"))
    destination_account = str(payload.get("toAccount") or payload["account"])
    destination_mailbox = str(payload.get("toMailboxPath") or payload.get("toMailbox"))
    if "/" in destination_mailbox:
        raise SystemExit("inline move only supports top-level destination mailboxes")
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var sourceAccount = app.accounts.byName(argv[0]);
  var sourceBox = sourceAccount.mailboxes.byName(argv[1]);
  var message = sourceBox.messages.byId(Number(argv[2]));
  var destAccount = app.accounts.byName(argv[3]);
  var destBox = destAccount.mailboxes.byName(argv[4]);
  app.move(message, {to: destBox});
  return JSON.stringify({
    ok: true,
    id: Number(argv[2]),
    account: sourceAccount.name(),
    mailbox: sourceBox.name(),
    mailboxPath: sourceBox.name(),
    toAccount: destAccount.name(),
    toMailbox: destBox.name(),
    toMailboxPath: destBox.name()
  });
}
'''
    return run_jxa_inline(
        script,
        [str(payload["account"]), source_mailbox, str(payload["id"]), destination_account, destination_mailbox],
    )


def inline_archive(payload: dict) -> dict:
    destination_mailboxes = ["Archive", "Archives", "All Mail", "归档", "存档", "已归档"]
    explicit = payload.get("archiveMailboxPath") or payload.get("archiveMailbox")
    if explicit:
        destination_mailboxes = [str(explicit)]
    last_error = None
    for mailbox_name in destination_mailboxes:
        try:
            next_payload = dict(payload)
            next_payload["toAccount"] = payload["account"]
            next_payload["toMailbox"] = mailbox_name
            next_payload["toMailboxPath"] = mailbox_name
            return inline_move(next_payload)
        except SystemExit as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise SystemExit("archive mailbox not found")


def inline_delete(payload: dict) -> dict:
    mailbox = str(payload.get("mailboxPath") or payload.get("mailbox"))
    script = r'''
function run(argv) {
  var app = Application("Mail");
  var account = app.accounts.byName(argv[0]);
  var box = account.mailboxes.byName(argv[1]);
  var message = box.messages.byId(Number(argv[2]));
  app.delete(message);
  return JSON.stringify({
    ok: true,
    id: Number(argv[2]),
    account: account.name(),
    mailbox: box.name(),
    mailboxPath: box.name()
  });
}
'''
    return run_jxa_inline(script, [str(payload["account"]), mailbox, str(payload["id"])])


def fast_search(payload: dict) -> list[dict]:
    query = str(payload.get("query") or "").strip()
    requested_limit = int(payload.get("limit", 20))
    scan_limit = int(payload.get("maxScanPerBox") or max(requested_limit * 8, 40))
    context_limit = max(requested_limit * 2, 10)
    items = collect_search_items(payload, scan_limit=scan_limit, context_limit=context_limit, query=query)
    if not payload.get("includeRead"):
        items = [item for item in items if not item.get("read")]
    return search_meta_items(items, query=query, limit=requested_limit)


def fast_search_with_body(payload: dict) -> list[dict]:
    query = str(payload.get("query") or "").strip()
    requested_limit = int(payload.get("limit", 20))
    context_limit = max(requested_limit * 2, 10)
    explicit_scan_limit = payload.get("maxScanPerBox")

    if explicit_scan_limit is not None:
        scan_limit = int(explicit_scan_limit)
        items = collect_search_items_with_body(
            payload,
            scan_limit=scan_limit,
            context_limit=context_limit,
            body_scan_limit=max(requested_limit * 4, 20),
            context_scan_limit=scan_limit,
            query=query,
        )
    else:
        primary_scan_limit = max(requested_limit * 4, 24)
        expanded_scan_limit = max(requested_limit * 6, 24)
        items = collect_search_items_with_body(
            payload,
            scan_limit=primary_scan_limit,
            context_limit=context_limit,
            body_scan_limit=max(requested_limit * 4, 20),
            context_scan_limit=expanded_scan_limit,
            query=query,
        )
        if not items and expanded_scan_limit > primary_scan_limit:
            items = collect_search_items_with_body(
                payload,
                scan_limit=expanded_scan_limit,
                context_limit=context_limit,
                body_scan_limit=max(requested_limit * 6, 24),
                context_scan_limit=expanded_scan_limit,
                query=query,
            )
    if not payload.get("includeRead"):
        items = [item for item in items if not item.get("read")]
    return search_meta_items(items, query=query, limit=requested_limit)


def collect_meta_items(payload: dict, *, limit: int, include_thread: bool) -> list[dict]:
    mailbox_name = str(payload.get("mailboxPath") or payload.get("mailbox") or "INBOX")
    if payload.get("account"):
        accounts = [str(payload["account"])]
    else:
        accounts = list_account_names_fast()
    items: list[dict] = []
    for account_name in accounts:
        try:
            rows = inline_triage_meta_for_account(account_name, mailbox_name, limit)
        except SystemExit:
            continue
        for row in rows:
            headers = str(row.pop("allHeaders", "") or "")
            if include_thread:
                items.append(build_search_meta_item(row, headers))
            else:
                items.append(build_triage_meta_item(row, headers))
    return items


def score_basic_row(row: dict, query: str) -> int:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return 0
    haystacks = [
        str(row.get("subject") or "").lower(),
        normalize_thread_subject(str(row.get("subject") or "")),
        str(row.get("sender") or "").lower(),
        str(row.get("messageId") or "").lower(),
    ]
    score = 0
    if normalized_query in haystacks[3]:
        score += 120
    if normalized_query in haystacks[0]:
        score += 90
    if normalized_query in haystacks[1]:
        score += 70
    if normalized_query in haystacks[2]:
        score += 80
    return score


def select_context_rows(rows: list[dict], direct_rows: list[dict], limit: int) -> list[dict]:
    direct_ids = {row.get("id") for row in direct_rows}
    direct_subjects = {
        normalize_thread_subject(str(row.get("subject") or ""))
        for row in direct_rows
        if row.get("subject")
    }
    selected: list[dict] = []
    for row in rows:
        subject_base = normalize_thread_subject(str(row.get("subject") or ""))
        if row.get("id") in direct_ids or (subject_base and subject_base in direct_subjects):
            selected.append(row)
    return selected[:limit]


def select_body_candidate_rows(rows: list[dict], direct_rows: list[dict], limit: int) -> list[dict]:
    selected: list[dict] = []
    seen_ids: set[object] = set()
    direct_ids = {row.get("id") for row in direct_rows}
    for row in rows:
        if row.get("id") in direct_ids and row.get("id") not in seen_ids:
            selected.append(row)
            seen_ids.add(row.get("id"))
    for row in rows:
        if row.get("id") in seen_ids:
            continue
        selected.append(row)
        seen_ids.add(row.get("id"))
        if len(selected) >= limit:
            break
    return selected[:limit]


def enrich_rows_with_headers(rows: list[dict], *, account: str, mailbox: str) -> list[dict]:
    header_rows = inline_headers_for_messages(account, mailbox, [int(row["id"]) for row in rows if row.get("id") is not None])
    headers_by_id = {header_row.get("id"): str(header_row.get("allHeaders") or "") for header_row in header_rows}
    items: list[dict] = []
    for row in rows:
        headers = headers_by_id.get(row.get("id"), "")
        items.append(build_search_meta_item(row, headers))
    return items


def mark_body_hits(items: list[dict], body_hit_ids: set[int]) -> list[dict]:
    output: list[dict] = []
    for item in items:
        next_item = dict(item)
        if item.get("id") in body_hit_ids:
            next_item["bodyHit"] = True
        output.append(next_item)
    return output


def find_body_hit_ids(body_rows: list[dict], query: str) -> set[int]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return set()
    hits: set[int] = set()
    for row in body_rows:
        content = str(row.get("content") or "").lower()
        if normalized_query in content and row.get("id") is not None:
            hits.add(int(row["id"]))
    return hits


def find_body_hit_ids_batched(
    account: str,
    mailbox: str,
    rows: list[dict],
    query: str,
    *,
    max_hits: int,
    batch_size: int = 8,
) -> set[int]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return set()
    hits: set[int] = set()
    message_ids = [int(row["id"]) for row in rows if row.get("id") is not None]
    for start in range(0, len(message_ids), max(1, batch_size)):
        batch_ids = message_ids[start : start + max(1, batch_size)]
        try:
            body_rows = inline_bodies_for_messages(account, mailbox, batch_ids)
        except SystemExit:
            continue
        hits |= find_body_hit_ids(body_rows, normalized_query)
        if len(hits) >= max_hits:
            break
    return hits


def collect_search_items(payload: dict, *, scan_limit: int, context_limit: int, query: str) -> list[dict]:
    mailbox_name = str(payload.get("mailboxPath") or payload.get("mailbox") or "INBOX")
    include_accounts = [str(payload["account"])] if payload.get("account") else list_account_names_fast()
    items: list[dict] = []
    for account_name in include_accounts:
        try:
            rows = search_recent_rows_for_account(account_name, mailbox_name, scan_limit)
        except SystemExit:
            continue
        direct_rows = [row for row in rows if score_basic_row(row, query) > 0]
        if direct_rows:
            selected_rows = select_context_rows(rows, direct_rows, limit=max(context_limit, len(direct_rows)))
            items.extend(enrich_rows_with_headers(selected_rows, account=account_name, mailbox=mailbox_name))
            continue
        try:
            fallback_rows = inline_triage_meta_for_account(account_name, mailbox_name, context_limit)
        except SystemExit:
            continue
        for row in fallback_rows:
            headers = str(row.pop("allHeaders", "") or "")
            items.append(build_search_meta_item(row, headers))
    return items


def collect_search_items_with_body(
    payload: dict,
    *,
    scan_limit: int,
    context_limit: int,
    body_scan_limit: int,
    context_scan_limit: int | None,
    query: str,
) -> list[dict]:
    mailbox_name = str(payload.get("mailboxPath") or payload.get("mailbox") or "INBOX")
    include_accounts = [str(payload["account"])] if payload.get("account") else list_account_names_fast()
    items: list[dict] = []
    for account_name in include_accounts:
        try:
            rows = search_recent_rows_for_account(account_name, mailbox_name, scan_limit)
        except SystemExit:
            continue
        metadata_direct_rows = [row for row in rows if score_basic_row(row, query) > 0]
        candidate_rows = select_body_candidate_rows(rows, metadata_direct_rows, body_scan_limit)
        body_hit_ids = find_body_hit_ids_batched(
            account_name,
            mailbox_name,
            candidate_rows,
            query,
            max_hits=max(1, context_limit // 2),
        )
        direct_ids = {int(row["id"]) for row in metadata_direct_rows if row.get("id") is not None} | body_hit_ids
        if not direct_ids:
            continue
        context_rows = rows
        if metadata_direct_rows and context_scan_limit and context_scan_limit > len(rows):
            try:
                extra_rows = search_recent_rows_for_account(
                    account_name,
                    mailbox_name,
                    context_scan_limit - len(rows),
                    start_index=len(rows) + 1,
                )
            except SystemExit:
                extra_rows = []
            context_rows = rows + extra_rows
        direct_rows = [row for row in context_rows if row.get("id") in direct_ids]
        selected_rows = select_context_rows(context_rows, direct_rows, limit=max(context_limit, len(direct_rows)))
        account_items = enrich_rows_with_headers(selected_rows, account=account_name, mailbox=mailbox_name)
        items.extend(mark_body_hits(account_items, body_hit_ids))
    return items


def triage_meta(payload: dict) -> list[dict]:
    requested_limit = int(payload.get("limit", 20))
    include_read = bool(payload.get("includeRead"))
    on_date = payload.get("onDate")
    per_account_limit = int(payload.get("maxScanPerBox") or max(requested_limit, 5))
    items = collect_meta_items(payload, limit=per_account_limit, include_thread=False)
    return filter_triage_items(items, on_date=str(on_date) if on_date else None, include_read=include_read)[:requested_limit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apple-apps")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    domains = parser.add_subparsers(dest="domain", required=True)
    mail = domains.add_parser("mail", help="Manage Apple Mail")
    mail_actions = mail.add_subparsers(dest="mail_action", required=True)

    mail_actions.add_parser("accounts", help="List Mail accounts")

    mailboxes = mail_actions.add_parser("mailboxes", help="List mailboxes for an account")
    mailboxes.add_argument("--account", required=True, help="Mail account name")

    recent = mail_actions.add_parser("recent", help="List recent messages")
    add_mailbox_locator(recent, account_required=False)
    recent.add_argument("--limit", type=int, default=20)
    recent.add_argument("--include-read", action="store_true")
    recent.add_argument("--max-scan-per-box", type=int, default=None)

    search = mail_actions.add_parser("search", help="Search recent messages")
    add_mailbox_locator(search, account_required=False)
    search.add_argument("--query", default="")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--include-read", action="store_true")
    search.add_argument("--include-body", action="store_true")
    search.add_argument("--max-scan-per-box", type=int, default=None)

    triage_meta_parser = mail_actions.add_parser("triage-meta", help="List lightweight metadata for triage")
    add_mailbox_locator(triage_meta_parser, account_required=False)
    triage_meta_parser.add_argument("--limit", type=int, default=20)
    triage_meta_parser.add_argument("--include-read", action="store_true")
    triage_meta_parser.add_argument("--on-date", help="Filter by local date in YYYY-MM-DD format")
    triage_meta_parser.add_argument("--max-scan-per-box", type=int, default=None)

    read = mail_actions.add_parser("read", help="Read one message")
    add_message_locator(read)

    mark = mail_actions.add_parser("mark", help="Mark one message read/unread or flagged/unflagged")
    add_message_locator(mark)
    mark.add_argument("--read", type=str_to_bool)
    mark.add_argument("--flagged", type=str_to_bool)

    move = mail_actions.add_parser("move", help="Move one message to another mailbox")
    add_message_locator(move)
    move.add_argument("--to-account", help="Destination account name; defaults to source account")
    move.add_argument("--to-mailbox", help="Destination mailbox name")
    move.add_argument("--to-mailbox-path", help="Destination mailbox path")

    archive = mail_actions.add_parser("archive", help="Archive one message")
    add_message_locator(archive)
    archive.add_argument("--archive-mailbox", help="Explicit archive mailbox name override")
    archive.add_argument("--archive-mailbox-path", help="Explicit archive mailbox path override")

    delete = mail_actions.add_parser("delete", help="Delete one message")
    add_message_locator(delete)

    return parser


def add_mailbox_locator(parser: argparse.ArgumentParser, *, account_required: bool) -> None:
    parser.add_argument("--account", required=account_required, help="Mail account name")
    parser.add_argument("--mailbox", help="Mailbox name")
    parser.add_argument("--mailbox-path", help="Mailbox path")


def add_message_locator(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True, help="Mail numeric message id")
    parser.add_argument("--account", required=True, help="Mail account name")
    parser.add_argument("--mailbox", help="Mailbox name")
    parser.add_argument("--mailbox-path", help="Mailbox path")


def args_to_payload(namespace: argparse.Namespace) -> dict:
    payload = {}
    for key, value in vars(namespace).items():
        if key in {"pretty", "domain", "mail_action"}:
            continue
        if value is None:
            continue
        payload[KEY_MAP.get(key, key)] = value
    return payload


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.domain != "mail":
        parser.error(f"unsupported domain: {args.domain}")

    if args.mail_action == "mark" and args.read is None and args.flagged is None:
        parser.error("mail mark requires --read and/or --flagged")

    if args.mail_action == "move" and not args.to_mailbox and not args.to_mailbox_path:
        parser.error("mail move requires --to-mailbox or --to-mailbox-path")

    payload = args_to_payload(args)
    if args.mail_action == "recent" and can_use_fast_recent(payload):
        result = fast_recent(payload)
    elif args.mail_action == "search" and can_use_fast_recent(payload) and payload.get("includeBody"):
        result = fast_search_with_body(payload)
    elif args.mail_action == "search" and can_use_fast_recent(payload) and not payload.get("includeBody"):
        result = fast_search(payload)
    elif args.mail_action == "triage-meta":
        result = triage_meta(payload)
    elif args.mail_action == "read" and can_use_inline_mailbox(payload):
        result = inline_read(payload)
    elif args.mail_action == "mark" and can_use_inline_mailbox(payload):
        result = inline_mark(payload)
    elif args.mail_action == "move" and can_use_inline_mailbox(payload) and can_use_inline_mailbox({"account": payload.get("toAccount") or payload.get("account"), "mailboxPath": payload.get("toMailboxPath") or payload.get("toMailbox")}):
        result = inline_move(payload)
    elif args.mail_action == "archive" and can_use_inline_mailbox(payload):
        result = inline_archive(payload)
    elif args.mail_action == "delete" and can_use_inline_mailbox(payload):
        result = inline_delete(payload)
    else:
        result = run_mail(args.mail_action, payload)
    dump_json(result, pretty=args.pretty)
    return 0


def dump_json(value: object, *, pretty: bool) -> None:
    if pretty:
        json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    else:
        json.dump(value, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
