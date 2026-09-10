"""Fail-closed bundle verification tests (Phase A security hardening).

Regression coverage for the audit finding: verify_bundle used to report
extra unmanifested ZIP members but still return ``valid=true``, so an
injected unchecksummed member could be accepted. Extra members are now
rejected by default; manifest grammar, duplicate members, unsafe names
and archive safety caps are enforced.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from aihwbench import bundles as bundles_mod
from aihwbench.bundles import create_bundle, verify_bundle


def _result(run_id: str = "run-1") -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp": "2026-01-01T00:00:00Z",
        "runtime": {"name": "ollama", "version": "0.5.0"},
        "model": {"name": "m", "format": "gguf"},
        "metrics": {"generation_tokens_per_second": 10.0},
    }


def _rewrite(path, names, mutate=None):
    """Rewrite a zip with the given member names, applying an optional
    mutation that may add or replace members (name -> bytes)."""
    with zipfile.ZipFile(path) as zf:
        contents = {n: zf.read(n) for n in zf.namelist()}
    if mutate:
        contents = mutate(contents)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for n, data in contents.items():
            zf.writestr(n, data)


def test_roundtrip_bundle_is_valid(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    report = verify_bundle(path)
    assert report["valid"] is True
    assert report["policy"] == "strict"
    assert report["violations"] == []
    assert report["manifest_errors"] == []


def test_injected_unmanifested_member_is_rejected(tmp_path):
    """P0 regression: an unchecksummed injected member must invalidate."""
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {**c, "injected.json": b'{"evil": true}'},
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert report["extra_members"] == ["injected.json"]
    assert report["policy"] == "extra members rejected"


def test_extra_members_opt_in_reports_but_tolerates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(path, None, mutate=lambda c: {**c, "extra.txt": b"hello"})
    report = verify_bundle(path, allow_extra_members=True)
    assert report["valid"] is True
    assert report["extra_members"] == ["extra.txt"]
    assert "tolerated" in report["policy"]


def test_duplicate_manifest_entry_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {
            **c,
            "MANIFEST.sha256": c["MANIFEST.sha256"] + c["MANIFEST.sha256"].splitlines()[0] + b"\n",
        },
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("duplicate" in e for e in report["manifest_errors"])


def test_malformed_manifest_digest_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {
            **c,
            "MANIFEST.sha256": b"deadbeef  result.json\n",
        },
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert report["manifest_errors"]


def test_traversal_member_name_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    _rewrite(
        path,
        None,
        mutate=lambda c: {**c, "../evil.json": b"x"},
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("unsafe member name" in v for v in report["violations"])


def test_member_count_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(bundles_mod, "MAX_MEMBER_COUNT", 2)
    path = create_bundle(
        tmp_path / "run.aihwbench",
        _result(),
        environment={"os": "linux"},
        workload={"id": "w"},
        telemetry={"samples": 1},
    )
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("member count" in v for v in report["violations"])


def test_compression_ratio_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(bundles_mod, "MAX_COMPRESSION_RATIO", 10.0)
    result = _result()
    result["metrics"]["padding"] = "0" * 20000  # highly compressible
    path = create_bundle(tmp_path / "run.aihwbench", result)
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("compression ratio" in v for v in report["violations"])


def test_uncompressed_size_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(bundles_mod, "MAX_UNCOMPRESSED_BYTES", 64)
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("uncompressed size" in v for v in report["violations"])


def test_duplicate_member_names_invalidates(tmp_path):
    path = create_bundle(tmp_path / "run.aihwbench", _result())
    with zipfile.ZipFile(path) as zf:
        contents = {n: zf.read(n) for n in zf.namelist()}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for n, data in contents.items():
            zf.writestr(n, data)
        with pytest.warns(UserWarning, match="Duplicate name"):
            zf.writestr("result.json", json.dumps(_result("dup")).encode("utf-8"))
    report = verify_bundle(path)
    assert report["valid"] is False
    assert any("duplicate member names" in v for v in report["violations"])


def test_missing_bundle_file_reports_reason(tmp_path):
    report = verify_bundle(tmp_path / "does-not-exist.aihwbench")
    assert report["valid"] is False
    assert report["reason"] == "bundle not found"


# ------------------------------------------------------------- signing
#
# sign_bundle_cosign and verify_bundle_cosign shipped with no callers outside
# tests: `aihwbench bundle` exposed no --sign, so a bundle could carry
# checksums and never a signature. Checksums show a bundle is internally
# consistent; anyone who edits the contents can recompute them. The signature
# is the part that carries authorship.


def test_bundle_signing_is_reachable_from_the_cli():
    from aihwbench.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["bundle", "r.json", "--sign", "--key", "k"])
    assert args.sign is True
    assert args.key == "k"


def test_verify_bundle_can_require_a_signature():
    from aihwbench.cli import build_parser

    args = build_parser().parse_args(["verify-bundle", "b.aihwbench", "--verify-signature"])
    assert args.verify_signature is True


def test_signing_without_cosign_is_a_configuration_error(tmp_path, monkeypatch):
    """The bundle is valid; the environment is not. Those are different."""
    import json

    from aihwbench.cli import main
    from tests.test_ecosystem import _result

    source = tmp_path / "r.json"
    source.write_text(json.dumps(_result("sign-me", 100.0)), encoding="utf-8")

    monkeypatch.setattr(
        "aihwbench.cli.repro.sign_bundle_cosign",
        lambda *a, **k: {
            "signed": False,
            "reason": "cosign not installed",
        },
    )
    code = main(["bundle", str(source), "--output", str(tmp_path / "r.aihwbench"), "--sign"])
    assert code == 4  # EXIT_CONFIGURATION_ERROR, not a validation failure
    assert (tmp_path / "r.aihwbench").is_file(), "the bundle must still be written"


def test_a_successful_signature_is_written_beside_the_bundle(tmp_path, monkeypatch):
    import json

    from aihwbench.cli import main
    from tests.test_ecosystem import _result

    source = tmp_path / "r.json"
    source.write_text(json.dumps(_result("signed", 100.0)), encoding="utf-8")
    monkeypatch.setattr(
        "aihwbench.cli.repro.sign_bundle_cosign",
        lambda *a, **k: {
            "signed": True,
            "signature": "MEUCIQfake",
        },
    )

    bundle = tmp_path / "r.aihwbench"
    assert main(["bundle", str(source), "--output", str(bundle), "--sign"]) == 0
    signature = bundle.with_suffix(bundle.suffix + ".sig")
    assert signature.is_file()
    assert signature.read_text(encoding="utf-8").strip() == "MEUCIQfake"


def test_a_failed_signature_check_invalidates_the_bundle(tmp_path, monkeypatch):
    """Checksums passing while the signature fails is the case this catches."""
    import json

    from aihwbench.cli import main
    from tests.test_ecosystem import _result

    source = tmp_path / "r.json"
    source.write_text(json.dumps(_result("tampered", 100.0)), encoding="utf-8")
    bundle = tmp_path / "r.aihwbench"
    assert main(["bundle", str(source), "--output", str(bundle)]) == 0

    monkeypatch.setattr(
        "aihwbench.cli.repro.verify_bundle_cosign",
        lambda *a, **k: {
            "verified": False,
            "output": "signature mismatch",
        },
    )
    assert main(["verify-bundle", str(bundle), "--verify-signature"]) == 1


# --- What a passing verification actually establishes ------------------------
#
# The manifest ships *inside* the bundle, so anyone who edits a member can
# recompute it. `valid: true` therefore means the contents match the checksums
# that travelled with them — not that either is authentic. That is inherent to
# any unsigned checksum scheme; what matters is that the report says so
# rather than leaving `valid: true` to be read as "this is genuine".


def test_a_rebuilt_manifest_verifies_clean(tmp_path):
    """The limit of unsigned integrity, demonstrated rather than assumed."""
    import hashlib

    path = create_bundle(tmp_path / "b.aihwbench", _result())

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        members = {name: zf.read(name) for name in names}

    doc = json.loads(members["result.json"].decode("utf-8"))
    doc["metrics"]["generation_tokens_per_second"] = 9999.0
    forged = json.dumps(doc, indent=2).encode("utf-8")
    digest = hashlib.sha256(forged).hexdigest()

    forged_path = tmp_path / "forged.aihwbench"
    with zipfile.ZipFile(forged_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("result.json", forged)
        zf.writestr("MANIFEST.sha256", f"{digest}  result.json\n")

    report = verify_bundle(forged_path)
    assert report["valid"] is True  # checksums match, because they were rewritten
    assert report["signature_checked"] is False
    # ...and the report does not let that pass for authenticity.
    assert "not a deliberately rebuilt bundle" in report["attests"]
    assert "--verify-signature" in report["attests"]


def test_an_untouched_bundle_says_what_it_checked(tmp_path):
    path = create_bundle(tmp_path / "b.aihwbench", _result())

    report = verify_bundle(path)
    assert report["valid"] is True
    assert report["signature_checked"] is False
    assert "corruption" in report["attests"]


def test_editing_a_member_without_the_manifest_is_caught(tmp_path):
    """The case unsigned checksums do catch, and the common one."""
    path = create_bundle(tmp_path / "b.aihwbench", _result())

    with zipfile.ZipFile(path) as zf:
        members = {name: zf.read(name) for name in zf.namelist()}

    doc = json.loads(members["result.json"].decode("utf-8"))
    doc["metrics"]["generation_tokens_per_second"] = 9999.0

    tampered = tmp_path / "tampered.aihwbench"
    with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("result.json", json.dumps(doc, indent=2))
        zf.writestr("MANIFEST.sha256", members["MANIFEST.sha256"])

    report = verify_bundle(tampered)
    assert report["valid"] is False
    assert "result.json" in report["mismatches"]
