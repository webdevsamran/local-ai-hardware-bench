"""Reproducibility and trust commands: bundles, environment diffs,
reproduction checks, repro scores and self-tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..bundles import create_bundle, verify_bundle
from ..exit_codes import EXIT_CONFIGURATION_ERROR, EXIT_OK, EXIT_VALIDATION_ERROR
from ..provenance import compute_provenance, sign_bundle_cosign, verify_bundle_cosign
from ..repro import check_reproduction, env_diff, reproducibility_score
from ..selftest import run_self_test
from ..system_info import detect_system
from ..validate import load_result
from .common import echo_json, fail


def cmd_bundle(args: argparse.Namespace) -> int:
    """Create a portable .aihwbench bundle (#36)."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    result = dict(result)
    result.setdefault("provenance", compute_provenance(result))
    env_path = Path(args.environment) if args.environment else None
    environment = json.loads(env_path.read_text(encoding="utf-8")) if env_path else None
    out_path = Path(args.output or Path(args.result).with_suffix(".aihwbench"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path = create_bundle(out_path, result, environment=environment)
    print(f"Bundle created: {bundle_path}")
    verification = verify_bundle(bundle_path)

    if args.sign:
        # Checksums prove a bundle is internally consistent; they say nothing
        # about who produced it, because anyone who edits the contents can
        # recompute them. A signature is the part that carries authorship.
        signature = sign_bundle_cosign(bundle_path, key_ref=args.key)
        verification["signature"] = signature
        if not signature["signed"]:
            fail(
                "signing failed: "
                + (signature.get("reason") or signature.get("stderr") or "unknown error")
                + ". The bundle was written and is valid; it is simply unsigned."
            )
            echo_json(verification)
            # The bundle itself is fine, so this is a configuration error
            # rather than an invalid artifact.
            return EXIT_CONFIGURATION_ERROR
        signature_path = bundle_path.with_suffix(bundle_path.suffix + ".sig")
        signature_path.write_text(signature["signature"] + "\n", encoding="utf-8")
        print(f"Signature written: {signature_path}")

    echo_json(verification)
    return EXIT_OK if verification["valid"] else EXIT_VALIDATION_ERROR


def cmd_verify_bundle(args: argparse.Namespace) -> int:
    """Verify bundle integrity (checksums), and its signature when asked."""
    bundle_path = Path(args.bundle)
    report = verify_bundle(bundle_path)

    if args.signature or args.verify_signature:
        signature_path = Path(args.signature) if args.signature else None
        if signature_path is None:
            candidate = bundle_path.with_suffix(bundle_path.suffix + ".sig")
            signature_path = candidate if candidate.is_file() else None
        report["signature"] = verify_bundle_cosign(bundle_path, signature_path)
        report["signature_checked"] = True
        report["attests"] = (
            "contents match the manifest, and the bundle's signature was checked"
            if report["signature"]["verified"]
            else "signature verification failed"
        )
        if not report["signature"]["verified"]:
            # An unverified signature is a failure of the whole check: a
            # bundle whose checksums pass but whose signature does not is
            # exactly the case this exists to catch.
            report["valid"] = False

    echo_json(report)
    return EXIT_OK if report["valid"] else EXIT_VALIDATION_ERROR


def cmd_env_diff(args: argparse.Namespace) -> int:
    """Show matching/differing fields between two results (#33)."""
    try:
        a = load_result(Path(args.result_a))
        b = load_result(Path(args.result_b))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    echo_json(env_diff(a, b))
    return EXIT_OK


def cmd_reproduce(args: argparse.Namespace) -> int:
    """Check reproduction prerequisites for a result (#34)."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    system = detect_system() if args.check_environment else {}
    echo_json(check_reproduction(result, system))
    return EXIT_OK


def cmd_repro_score(args: argparse.Namespace) -> int:
    """Reproducibility metadata-completeness score (#35)."""
    try:
        result = load_result(Path(args.result))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return EXIT_VALIDATION_ERROR
    echo_json(reproducibility_score(result))
    return EXIT_OK


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Precondition and environment-noise checks (#49)."""
    report = run_self_test()
    echo_json(report)
    return EXIT_OK if report["overall"] != "fail" else EXIT_CONFIGURATION_ERROR


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    bun = sub.add_parser("bundle", help="Create a portable .aihwbench bundle")
    bun.add_argument("result")
    bun.add_argument("--environment", default=None, help="Optional environment.json")
    bun.add_argument("--output", default=None, help="Output bundle path")
    bun.add_argument(
        "--sign",
        action="store_true",
        help=(
            "sign the bundle with cosign (keyless by default). Checksums show "
            "a bundle is internally consistent; a signature is what carries "
            "authorship."
        ),
    )
    bun.add_argument(
        "--key",
        default=None,
        help="cosign key reference; omit for keyless signing",
    )
    bun.set_defaults(func=cmd_bundle)

    vbun = sub.add_parser("verify-bundle", help="Verify .aihwbench bundle integrity")
    vbun.add_argument("bundle")
    vbun.add_argument(
        "--signature",
        default=None,
        help="Signature file; defaults to <bundle>.sig when it exists",
    )
    vbun.add_argument(
        "--verify-signature",
        action="store_true",
        help="Require a valid signature, not just matching checksums",
    )
    vbun.set_defaults(func=cmd_verify_bundle)

    ediff = sub.add_parser("env-diff", help="Diff two result environments")
    ediff.add_argument("result_a")
    ediff.add_argument("result_b")
    ediff.set_defaults(func=cmd_env_diff)

    repro_p = sub.add_parser("reproduce", help="Check reproduction prerequisites")
    repro_p.add_argument("result")
    repro_p.add_argument(
        "--check-environment",
        action="store_true",
        help="Compare against this machine's detected system",
    )
    repro_p.set_defaults(func=cmd_reproduce)

    rscore = sub.add_parser("repro-score", help="Reproducibility completeness score")
    rscore.add_argument("result")
    rscore.set_defaults(func=cmd_repro_score)

    sub.add_parser("self-test", help="Benchmark precondition / noise checks").set_defaults(
        func=cmd_self_test
    )
