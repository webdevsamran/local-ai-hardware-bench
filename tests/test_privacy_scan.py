"""Fix 6 verification — unified recursive privacy scanner.

Proves the two P0 defect fixes:

1. Findings are redacted: a leaked secret never appears verbatim in any
   finding string (the old scanner echoed ``match.group(0)!r``).
2. Scanning is structural: nested strings are found with their JSON
   path preserved (the old ``quality.py`` flattened via ``repr()``, and
   the old ``sanitize.py`` scanned stringified objects).

Also pins the back-compat contracts consumed by CI and other tests:
``scan_object`` -> ``(clean, findings)`` with label substrings, and
``data_quality_report`` -> ``privacy_hits`` as canonical pattern ids.
"""

from __future__ import annotations

import json
from pathlib import Path

from aihwbench.quality import data_quality_report
from aihwbench.sanitize import (
    PATTERN_IDS,
    redact_match,
    scan_file,
    scan_object,
    scan_object_detailed,
)

GITHUB_TOKEN = "ghp_" + "a" * 36


def test_token_detected_and_redacted():
    clean, findings = scan_object({"config": {"api_key": GITHUB_TOKEN}})
    assert not clean
    assert len(findings) == 1
    # The secret itself must never appear in any finding string.
    assert GITHUB_TOKEN not in findings[0]
    assert "aaaa" not in findings[0]
    assert "redacted" in findings[0]
    assert "token" in findings[0].lower()


def test_bearer_token_detected_in_nested_list():
    doc = {"headers": ["Accept: application/json", "Authorization: Bearer abc123def456ghi"]}
    detailed = scan_object_detailed(doc)
    assert [f["pattern"] for f in detailed] == ["token_or_credential"]
    assert detailed[0]["path"] == "$.headers[1]"


def test_structural_paths_preserved_for_nested_leaks():
    doc = {"metrics": {"notes": [{"text": "device SN12345678 serial"}]}}
    detailed = scan_object_detailed(doc)
    assert any(f["path"] == "$.metrics.notes[0].text" for f in detailed)
    assert any(f["pattern"] == "serial_like" for f in detailed)


def test_numbers_and_null_are_not_scanned():
    assert scan_object_detailed({"n": None, "f": 1.5, "i": 12345678, "b": True}) == []


def test_windows_path_detected_on_any_host_os():
    # Detection is pattern-based, not os.path-based: a Windows user path
    # must be found even when the scanner runs on Linux/macOS.
    raw = "C:" + chr(92) + "Users" + chr(92) + "alice" + chr(92) + "models"
    clean, findings = scan_object({"path": raw})
    assert not clean
    assert any("home" in f.lower() for f in findings)


def test_repr_doubled_windows_path_still_detected():
    # Values that passed through repr() double their backslashes; the
    # one-or-more quantifier must still catch them.
    raw = "C:" + chr(92) * 2 + "Users" + chr(92) * 2 + "alice"
    clean, findings = scan_object({"path": raw})
    assert not clean
    assert any("home" in f.lower() for f in findings)


def test_posix_home_path_detected():
    clean, findings = scan_object({"cmd": "export HF_HOME=/home/alice/.cache"})
    assert not clean
    assert any("home" in f.lower() for f in findings)


def test_mac_address_and_email_detected():
    clean, findings = scan_object({"mac": "00:1A:2B:3C:4D:5E", "contact": "person@example.com"})
    assert not clean
    assert any("MAC" in f for f in findings)
    assert any("email" in f.lower() for f in findings)


def test_key_names_are_scanned_too():
    detailed = scan_object_detailed({"serial number": "SN123456789"})
    assert any(f["pattern"] == "serial_like" for f in detailed)


def test_scan_object_back_compat_contract():
    clean, findings = scan_object({"note": "reach me at me@example.org"})
    assert clean is False
    assert all(isinstance(f, str) for f in findings)
    # Clean object yields exactly (True, []).
    assert scan_object({"throughput": 42.0}) == (True, [])


def test_pattern_ids_are_stable_and_ordered():
    assert PATTERN_IDS[0] == "mac_address"
    assert "windows_path" in PATTERN_IDS
    assert "email" in PATTERN_IDS


def test_redact_match_unit():
    assert redact_match("abcd") == "[redacted len=4]"
    out = redact_match("abcdefghij")
    assert out.startswith("abcd") and "redacted len=10" in out
    assert "efghij" not in out


def test_scan_file_json_structural(tmp_path: Path):
    doc = {"system": {"platform_name": "C:" + chr(92) + "Users" + chr(92) + "bob"}}
    path = tmp_path / "leaky.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    clean, findings = scan_file(path)
    assert not clean
    assert any("$.system.platform_name" in f for f in findings)


def test_scan_file_raw_text_fallback(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("token: " + GITHUB_TOKEN, encoding="utf-8")
    clean, findings = scan_file(path)
    assert not clean
    assert all(GITHUB_TOKEN not in f for f in findings)


def test_scan_file_clean_json(tmp_path: Path):
    path = tmp_path / "clean.json"
    path.write_text(json.dumps({"metrics": {"ttft_ms": 12.5}}), encoding="utf-8")
    assert scan_file(path) == (True, [])


def test_quality_report_delegates_to_canonical_scanner():
    leaky = {
        "run_id": "r",
        "schema_version": "1.0",
        "timestamp": "2026-01-01T00:00:00Z",
        "reproducibility": {"command": "run C:" + chr(92) + "Users" + chr(92) + "sam"},
    }
    report = data_quality_report(leaky)
    checks = report["checks"]
    assert checks["privacy_clean"] is False
    assert "windows_path" in checks["privacy_hits"]
    # Ids come from the canonical registry, deduplicated, deterministic.
    assert checks["privacy_hits"] == list(dict.fromkeys(checks["privacy_hits"]))


def test_quality_report_clean_result_has_no_hits():
    report = data_quality_report(
        {
            "run_id": "r",
            "schema_version": "1.0",
            "timestamp": "2026-01-01T00:00:00Z",
            "metrics": {"ttft_ms": 10.0},
        }
    )
    assert report["checks"]["privacy_clean"] is True
    assert report["checks"]["privacy_hits"] == []
