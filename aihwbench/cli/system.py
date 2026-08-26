"""System and runtime detection commands."""

from __future__ import annotations

import argparse

from ..backends import detect_all
from ..exit_codes import EXIT_CONFIGURATION_ERROR, EXIT_OK
from ..system_info import detect_system
from .common import echo_json


def cmd_system_info(_args: argparse.Namespace) -> int:
    echo_json(detect_system())
    return EXIT_OK


def cmd_detect(_args: argparse.Namespace) -> int:
    echo_json({"system": detect_system(), "runtimes": detect_all()})
    return EXIT_OK


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Actionable hardware/runtime preconditions report."""
    system = detect_system()
    problems: list[str] = []
    if not system.get("cpu"):
        problems.append("CPU detection failed")
    if not system.get("gpu"):
        problems.append("No GPU detected")
    print("== System ==")
    for key, value in system.items():
        print(f"  {key}: {value}")
    print()
    print("== Runtimes ==")
    for info in detect_all():
        status = info["status"]
        print(f"  {info['name']:<14} {status:<24} {info.get('version') or '-'}")
        if info.get("detail"):
            print(f"  {'':<14} {info['detail']}")
    print()
    if problems:
        print("Recommendations:")
        for p in problems:
            print(f"  - {p}")
        return EXIT_CONFIGURATION_ERROR
    return EXIT_OK


def cmd_runtimes(_args: argparse.Namespace) -> int:
    for info in detect_all():
        status = info["status"]
        version = info.get("version") or "-"
        print(f"{info['name']:<14} {status:<24} {version}")
        if info.get("detail"):
            print(f"{'':<14} {info['detail']}")
    return EXIT_OK


def register(sub: argparse._SubParsersAction) -> None:
    sub.add_parser("system-info", help="Print detected hardware").set_defaults(func=cmd_system_info)
    sub.add_parser("detect", help="Full system + runtime detection as JSON").set_defaults(
        func=cmd_detect
    )
    sub.add_parser("doctor", help="Diagnose hardware/runtime preconditions").set_defaults(
        func=cmd_doctor
    )
    sub.add_parser("runtimes", help="List runtime backends and status").set_defaults(
        func=cmd_runtimes
    )
