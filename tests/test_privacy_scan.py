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
import re
from pathlib import Path

import pytest

from aihwbench.quality import data_quality_report
from aihwbench.sanitize import (
    PATTERN_IDS,
    redact_match,
    redact_object,
    redact_text,
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


# --------------------------------------------------------------- redaction
#
# Detection alone cannot protect a public dataset. A contributor needs to be
# able to *remove* a leak before submitting, because one leak in published
# data is unrecoverable.


def test_redaction_removes_every_finding():
    dirty = {
        "system": {"platform_name": "box of dev@example.com"},
        "note": r"C:\Users\alice\bench",
        "hosts": ["10.0.0.7", "aa:bb:cc:dd:ee:ff"],
    }
    assert not scan_object(dirty)[0], "fixture must start dirty"
    assert scan_object(redact_object(dirty))[0]


def test_redaction_is_idempotent():
    """The placeholder must not itself look like an identifier."""
    once = redact_object({"note": "mail dev@example.com from 10.0.0.7"})
    assert redact_object(once) == once


def test_redaction_keeps_no_prefix_of_the_secret():
    """Unlike a CI finding, published output must retain nothing of the value.

    `redact_match` deliberately keeps a short prefix so a reviewer can
    recognise a finding. That is exactly wrong for data being published.
    """
    cleaned = redact_text("contact alice.smith@example.com now")
    assert "alice" not in cleaned
    assert "example" not in cleaned
    assert "[redacted:email]" in cleaned


def test_redaction_replaces_every_occurrence_not_just_the_first():
    """The scanner reports one finding per pattern; scrubbing must remove all."""
    cleaned = redact_text("a@x.com and b@y.com and c@z.com")
    assert "@" not in cleaned
    assert cleaned.count("[redacted:email]") == 3


def test_redaction_preserves_non_string_scalars():
    """Numbers and booleans are measurements, not identifiers."""
    cleaned = redact_object({"latency_ms": 12.5, "ok": True, "missing": None})
    assert cleaned == {"latency_ms": 12.5, "ok": True, "missing": None}


def test_redaction_scrubs_dictionary_keys_too():
    """The scanner inspects keys, so redaction must as well."""
    cleaned = redact_object({r"C:\Users\bob\run": 1})
    assert not any("bob" in k for k in cleaned)


def test_colliding_keys_are_kept_rather_than_dropped():
    """Silently losing a field would be worse than an ugly key."""
    cleaned = redact_object({r"C:\Users\bob": 1, r"C:\Users\eve": 2})
    assert len(cleaned) == 2, "no field may be lost to a key collision"
    assert sorted(cleaned.values()) == [1, 2]


# --- path separators and platforms the scanner used to miss -----------------
#
# A result document is a public artifact in this project: it is committed to
# `results/published/` and served from the dataset API. So a home directory that
# slips past the scan is not an inconvenience, it is somebody's username on the
# internet. These four forms all did slip past.


@pytest.mark.parametrize(
    "leak,label",
    [
        (r"C:\Users\alice\models\m.gguf", "windows backslash"),
        ("C:/Users/alice/models/m.gguf", "windows forward slash"),
        (r"C:/Users/alice\models", "windows mixed separators"),
        ("/Users/alice/models", "macOS home"),
        ("/home/alice/models", "linux home"),
    ],
)
def test_every_home_directory_form_is_caught(leak, label):
    """Only the backslash form was.

    Windows accepts `/` everywhere, `pathlib` emits it, and JSON carries it
    without escaping — so `C:/Users/name/...` is the form this project actually
    produces, and it was the form that passed. macOS was worse: the posix
    pattern matches `/home/`, macOS uses `/Users/`, and nothing matched it at
    all. Every result from a Mac carried its owner's username, and this project
    ships an MLX backend whose entire audience is on macOS.
    """
    clean, findings = scan_object({"path": leak})
    assert not clean, f"{label} was not detected: {leak}"
    assert findings, f"{label} produced no finding"
    assert "alice" not in redact_object({"path": leak})["path"], f"{label} survived redaction"


@pytest.mark.parametrize(
    "secret",
    ["AKIAIOSFODNN7EXAMPLE", "ASIAY34FZKBOKMUTVV7A", "sk-proj-abc123def456ghi789jkl012"],
)
def test_cloud_and_api_keys_are_caught(secret):
    """A benchmark result should never carry one, and somebody will paste one
    into a note field anyway."""
    clean, _ = scan_object({"note": f"key {secret}"})
    assert not clean
    assert secret not in redact_object({"note": f"key {secret}"})["note"]


@pytest.mark.parametrize(
    "legitimate",
    [
        "sha256:bdffb86766b3da0a24c9de9f9da92ed79acb2b59fc93a5dd12cae6b2d1d48d04",
        "qwen2.5:0.5b-instruct-q4_K_M",
        "NVIDIA GeForce RTX 3080 Ti Laptop GPU",
        "models/mobilenetv2-12.onnx",
        "Users of this tool should run aihwbench doctor first",
        "exl2-4.65bpw",
    ],
)
def test_real_content_is_not_redacted(legitimate):
    """The cost of a greedy pattern is paid by every result.

    This project puts a SHA-256 digest in every document and a model tag in
    most; a checksum redacted as a "key" would destroy the provenance the
    checksum exists to provide.
    """
    clean, findings = scan_object({"v": legitimate})
    assert clean, f"false positive on legitimate content: {findings}"
    assert redact_object({"v": legitimate})["v"] == legitimate


# --------------------------------------------------------------------------
# The dashboard's own published data.
#
# `web/public/data/` is committed and served to every visitor, so it is a
# published artifact under exactly the rules `results/published/` lives by --
# and nothing was scanning it. One file carried the maintainer's real Windows
# account name, in a probe written to demonstrate the home-directory pattern.
# The scanner's own test corpus was the leak.
# --------------------------------------------------------------------------

_WEB_DATA = Path(__file__).resolve().parent.parent / "web" / "public" / "data"

#: The detection corpus is the one file here that is *supposed* to contain
#: identifiers: every probe in it exists to be matched. Scanning it would be
#: asserting that a fire drill is a fire.
_DETECTION_CORPUS = "privacy.json"


def _published_data_files() -> list[Path]:
    return sorted(p for p in _WEB_DATA.glob("*.json") if p.name != _DETECTION_CORPUS)


def test_there_are_published_data_files_to_scan():
    """A glob that matched nothing would make the test below vacuous."""
    assert len(_published_data_files()) >= 5


@pytest.mark.parametrize("path", _published_data_files(), ids=lambda p: p.name)
def test_published_dashboard_data_carries_no_identifiers(path: Path):
    clean, findings = scan_file(path)
    assert clean, f"{path.name} would publish: {findings}"


def test_the_detection_corpus_is_exempt_from_the_secret_scanner_by_marker():
    """Not by luck, and not by the scanner having a blind spot.

    Every probe in the corpus is a synthetic credential, which is precisely
    what `scripts/secret_scan.py` hunts for -- so it flagged this file, in CI,
    on every run, from the day the corpus was introduced. A permanently red
    check is worse than no check: it trains everyone to scroll past the one
    place a real secret would appear.

    The scanner already ships a whole-file exemption for a detection corpus.
    This pins that the generated document carries it, because the marker lives
    in generated output and the next regeneration is where it would be lost.
    """
    text = (_WEB_DATA / _DETECTION_CORPUS).read_text(encoding="utf-8")
    assert "secret-scan: allow-file" in text, (
        "the privacy corpus lost the secret scanner's whole-file exemption; "
        "regenerate it with scripts/generate_frontend_data.py"
    )


def test_the_generator_does_not_exempt_itself():
    """The marker exempts whatever file it appears in, including a generator.

    Writing it as a literal in `generate_frontend_data.py` made the generator
    itself exempt -- silently, and for every secret it might later come to
    hold. It is assembled from two halves there for this reason.
    """
    generator = Path(__file__).resolve().parent.parent / "scripts" / "generate_frontend_data.py"
    assert "secret-scan: allow-file" not in generator.read_text(encoding="utf-8"), (
        "generate_frontend_data.py contains the whole-file exemption marker "
        "verbatim, which exempts the generator itself from the secret scan"
    )


def test_the_secret_scanner_skips_gitignored_build_output():
    """`dist` was skipped and `dist-ssr` was not.

    Both are gitignored build output holding a second copy of every generated
    file. The effect was a scan whose result depended on whether the developer
    had run `npm run build` -- findings that appeared from nowhere and vanished
    again after `git clean`.
    """
    scanner = Path(__file__).resolve().parent.parent / "scripts" / "secret_scan.py"
    source = scanner.read_text(encoding="utf-8")
    for build_dir in ('"dist"', '"dist-ssr"', '"node_modules"'):
        assert build_dir in source, f"secret_scan.py no longer skips {build_dir}"


#: The only account name the detection corpus may use. A probe demonstrating a
#: home-directory pattern has to contain *some* username, and the tempting one
#: to reach for is whichever is on the machine writing it -- which is how the
#: maintainer's real Windows account name ended up committed and served to the
#: dashboard. `alice` was already the placeholder in the posix probe; this
#: makes it the only option rather than a convention.
_FICTIONAL_USER = "alice"

_HOME_PROBE = re.compile(r"(?:[A-Za-z]:)?[\\/]+(?:Users|home)[\\/]+([^\\/\s\"']+)", re.IGNORECASE)


def test_the_detection_corpus_names_only_a_fictional_user():
    """The one leak the scan above cannot catch, because it is inside the scan.

    `privacy.json` is excluded from the published-data scan by necessity: every
    probe in it is a deliberate identifier, so scanning it would fail by
    design. That exclusion is also a blind spot, and it is precisely where the
    real leak was -- a probe naming the maintainer's own Windows account under
    ``C:\\Users``, committed, published, and invisible to every check the
    project had.

    So the corpus gets its own narrower rule: a home-directory probe may name
    exactly one user, and that user is fictional.
    """
    corpus = json.loads((_WEB_DATA / _DETECTION_CORPUS).read_text(encoding="utf-8"))
    rules = corpus.get("privacy_rules", corpus)
    cases = rules["reference_cases"]
    assert cases, "the corpus has no reference cases to check"

    names = {
        match.group(1).lower() for case in cases for match in _HOME_PROBE.finditer(case["text"])
    }
    assert names, "no home-directory probe found; the corpus stopped covering the pattern"
    unexpected = sorted(names - {_FICTIONAL_USER})
    assert not unexpected, (
        f"the privacy corpus names {unexpected} in a home-directory probe. "
        f"Probes are published; use {_FICTIONAL_USER!r}, never a real account name."
    )
