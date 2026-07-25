#!/usr/bin/env python3
"""Bind generated-artifact QA evidence to a fresh file fingerprint."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def fingerprint(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"artifact is not a file: {path}")
    stat = resolved.stat()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(resolved),
        "mtime": stat.st_mtime,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": digest.hexdigest(),
    }


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def run_verify(args: argparse.Namespace) -> int:
    before = fingerprint(Path(args.artifact))
    completed = subprocess.run(args.command, check=False)
    after = fingerprint(Path(args.artifact))
    changed = before != after
    payload = {
        "artifact": str(Path(args.artifact).expanduser().resolve()),
        "before": before,
        "after": after,
        "qa_exit_code": completed.returncode,
        "artifact_changed_during_qa": changed,
        "qa_bound_to_fingerprint": None if changed else after,
    }
    print_json(payload)
    if changed:
        print(
            "artifact fingerprint changed during QA; rerun QA against the final artifact",
            file=sys.stderr,
        )
        return 2 if completed.returncode == 0 else completed.returncode
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    fp_parser = subparsers.add_parser("fingerprint", help="print artifact fingerprint JSON")
    fp_parser.add_argument("artifact")

    verify_parser = subparsers.add_parser("verify", help="run QA command after fingerprinting")
    verify_parser.add_argument("--artifact", required=True)
    verify_parser.add_argument("command", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    try:
        if args.command_name == "fingerprint":
            print_json(fingerprint(Path(args.artifact)))
            return 0
        if args.command_name == "verify":
            if args.command and args.command[0] == "--":
                args.command = args.command[1:]
            if not args.command:
                parser.error("verify requires a command after --")
            return run_verify(args)
    except (FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
