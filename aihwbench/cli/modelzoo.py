"""Model zoo commands: what was benchmarked, its licence, and how to get it."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..exit_codes import EXIT_OK, EXIT_USAGE_ERROR, EXIT_VALIDATION_ERROR
from ..modelzoo import DEFAULT_ZOO_PATH, ZooEntry, ZooError, fetch_entry, load_zoo, verify_entry
from .common import echo_json, fail


def _load(args: argparse.Namespace) -> list[ZooEntry] | None:
    try:
        return load_zoo(getattr(args, "manifest", None) or DEFAULT_ZOO_PATH)
    except ZooError as exc:
        fail(str(exc))
        return None


def _select(entries: list[ZooEntry], key: str | None) -> list[ZooEntry] | None:
    if key is None:
        return entries
    chosen = [e for e in entries if e.key == key]
    if not chosen:
        fail(f"no model with key {key!r}. Known keys: {', '.join(e.key for e in entries)}")
        return None
    return chosen


def cmd_zoo_list(args: argparse.Namespace) -> int:
    entries = _load(args)
    if entries is None:
        return EXIT_USAGE_ERROR
    if getattr(args, "json", False):
        echo_json([e.to_dict() for e in entries])
        return EXIT_OK
    print(f"{'KEY':<30} {'FORMAT':<7} {'LICENCE':<12} {'SOURCE':<11} SIZE")
    for entry in entries:
        size = f"{entry.size_bytes / 1e6:.1f} MB" if entry.size_bytes else "-"
        licence = entry.license or "unknown"
        # The provenance of a licence claim is shown next to it, because
        # "declared" means a human wrote it and nothing re-checks it.
        if entry.license_source == "declared":
            licence += "*"
        print(
            f"{entry.key:<30} {entry.format:<7} {licence:<12} "
            f"{str(entry.source.get('kind')):<11} {size}"
        )
    if any(e.license_source == "declared" for e in entries):
        print()
        print("* declared by a maintainer, not read from the artifact")
    return EXIT_OK


def cmd_zoo_verify(args: argparse.Namespace) -> int:
    entries = _load(args)
    if entries is None:
        return EXIT_USAGE_ERROR
    chosen = _select(entries, args.key)
    if chosen is None:
        return EXIT_USAGE_ERROR
    if args.path and len(chosen) != 1:
        fail("--path applies to a single model; name the key to verify")
        return EXIT_USAGE_ERROR

    reports = [verify_entry(e, args.path if args.path else None) for e in chosen]
    if getattr(args, "json", False):
        echo_json(reports)
    else:
        for report in reports:
            verified = report["verified"]
            mark = {True: "ok", False: "MISMATCH", None: "unchecked"}[verified]
            print(f"{report['key']:<30} {mark:<10} {report['reason']}")
            if report.get("license_matches") is False:
                print(f"{'':<30} {'LICENCE':<10} manifest and artifact disagree")

    # A mismatch is a failure. Unverified is not a pass either, but it is not
    # evidence of a wrong file, so it does not fail the command -- an entry
    # nobody can check locally would otherwise make `verify` permanently red.
    if any(r["verified"] is False or r.get("license_matches") is False for r in reports):
        return EXIT_VALIDATION_ERROR
    return EXIT_OK


def cmd_zoo_fetch(args: argparse.Namespace) -> int:
    entries = _load(args)
    if entries is None:
        return EXIT_USAGE_ERROR
    chosen = _select(entries, args.key)
    if chosen is None:
        return EXIT_USAGE_ERROR
    entry = chosen[0]

    if not entry.obtainable:
        fail(
            f"{entry.key} records no way to obtain it (source.kind is {entry.source.get('kind')!r})"
        )
        return EXIT_VALIDATION_ERROR

    where = entry.source.get("ref") or entry.source.get("url")
    print(f"fetching {entry.key} from {where}")
    if entry.license:
        print(f"licence: {entry.license} ({entry.license_source})")
        if entry.license_link:
            print(f"         {entry.license_link}")

    def progress(written: int) -> None:
        if entry.size_bytes:
            print(f"\r  {written / 1e6:.1f} / {entry.size_bytes / 1e6:.1f} MB", end="")

    try:
        report = fetch_entry(entry, Path(args.dest), on_progress=progress)
    except (OSError, ZooError) as exc:
        print()
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    print()
    print(report["reason"])
    return EXIT_OK if report.get("fetched") else EXIT_VALIDATION_ERROR


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    zoo = sub.add_parser(
        "zoo",
        help="Model zoo: licences, checksums, and how to obtain benchmarked models",
    )
    actions = zoo.add_subparsers(dest="zoo_command", required=True)

    listing = actions.add_parser("list", help="List models in the zoo manifest")
    listing.add_argument("--json", action="store_true", help="Emit the manifest as JSON")
    listing.set_defaults(func=cmd_zoo_list)

    verify = actions.add_parser(
        "verify",
        help="Check that a model is obtainable and unchanged",
    )
    verify.add_argument("key", nargs="?", help="Model key (default: every model)")
    verify.add_argument(
        "--path",
        help="Hash this file instead of asking the runtime where its copy is",
    )
    verify.add_argument("--json", action="store_true", help="Emit reports as JSON")
    verify.set_defaults(func=cmd_zoo_verify)

    fetch = actions.add_parser(
        "fetch",
        help="Download a model and verify it against the recorded checksum",
    )
    fetch.add_argument("key", help="Model key to fetch")
    fetch.add_argument("--dest", default="models", help="Directory to download into")
    fetch.set_defaults(func=cmd_zoo_fetch)

    for parser in (listing, verify, fetch):
        parser.add_argument(
            "--manifest",
            default=None,
            help=f"Zoo manifest path (default: {DEFAULT_ZOO_PATH})",
        )
