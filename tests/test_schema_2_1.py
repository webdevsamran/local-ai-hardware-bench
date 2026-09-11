"""Schema 2.1 requires what the classifier must read, and nothing more.

Schema 2.0 declared `model` with no `required` and `additionalProperties:
true`, and `reproducibility` as a nullable object with two optional
properties. So `{}` was a structurally valid result, and the classifier read
every absent field as agreement -- `_same(None, None)` is True by design --
which made two empty documents compare as STRICTLY_COMPARABLE with zero
reasons.

`comparability._REQUIRED_PRESENT` closes that at comparison time. This closes
it at the door, so a submission that cannot be compared is refused when it
arrives rather than silently compared anyway.

The two definitions are asserted against each other here, because a schema
that requires a different set from the gate is worse than one that requires
nothing: it would look like the rule was enforced.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from aihwbench.comparability import _REQUIRED_PRESENT
from aihwbench.formal_schema import load_formal_schema

SCHEMA = load_formal_schema("2.1")
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def _valid_document() -> dict:
    """The smallest document schema 2.1 accepts."""
    return {
        "schema_version": "2.1",
        "protocol_version": "1",
        "run_id": "r1",
        "timestamp": "2026-01-01T00:00:00Z",
        "system": {"cpu": "Test CPU"},
        "runtime": {"name": "llama.cpp", "backend": "cuda", "device": "cuda"},
        "model": {"name": "m.gguf"},
        "metrics": {"generation_tokens_per_second": 100.0},
        "reproducibility": {"iterations": 8, "warmup_runs": 3},
    }


def _errors(doc: dict) -> list[str]:
    return [e.message for e in VALIDATOR.iter_errors(doc)]


def test_the_schema_is_itself_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_a_minimal_complete_document_is_accepted():
    assert _errors(_valid_document()) == []


def test_the_empty_document_is_rejected():
    """The defect this version exists for.

    Under 2.0 this validated, and `compare_classification({}, {})` returned
    STRICTLY_COMPARABLE with no reasons.
    """
    assert _errors({})


@pytest.mark.parametrize("path", _REQUIRED_PRESENT)
def test_every_field_the_classifier_requires_is_required_by_the_schema(path):
    """Generated from the gate, so the two cannot drift apart."""
    block, field = path.split(".", 1)
    doc = _valid_document()
    del doc[block][field]
    errors = _errors(doc)
    assert errors, f"{path} is absent and the schema accepted the document"
    assert any(field in message for message in errors), errors


@pytest.mark.parametrize("path", _REQUIRED_PRESENT)
def test_a_null_in_a_required_field_is_rejected_like_an_absent_one(path):
    """`null` and absent are the same thing to the classifier.

    Requiring the key while allowing null would satisfy the schema and leave
    the hole exactly where it was.
    """
    block, field = path.split(".", 1)
    doc = _valid_document()
    doc[block][field] = None
    assert _errors(doc), f"{path} was null and the schema accepted it"


def test_a_null_block_cannot_stand_in_for_a_populated_one():
    """`required` applies only to objects.

    `reproducibility` was nullable in 2.0, so a document could set it to null
    and satisfy any `required` list inside it -- the rule would have been
    written and not enforced.
    """
    doc = _valid_document()
    doc["reproducibility"] = None
    assert _errors(doc)


def test_an_empty_string_is_rejected_in_a_required_string():
    """An empty name is a recorded absence, and compares as agreement."""
    for block, field in (("model", "name"), ("runtime", "name"), ("runtime", "device")):
        doc = _valid_document()
        doc[block][field] = ""
        assert _errors(doc), f"{block}.{field} was empty and the schema accepted it"


def test_zero_iterations_is_rejected():
    """A run with no measured iterations measured nothing."""
    doc = _valid_document()
    doc["reproducibility"]["iterations"] = 0
    assert _errors(doc)


def test_zero_warmups_is_allowed_because_it_is_a_real_choice():
    """It says the first, coldest iteration is in the reported figures."""
    doc = _valid_document()
    doc["reproducibility"]["warmup_runs"] = 0
    assert _errors(doc) == []


def test_the_schema_requires_no_more_than_the_gate_does():
    """Requiring extra fields would reject results the classifier can compare.

    The optional blocks stay optional: a machine with no power sensor, no
    container and no evaluator still produces a publishable result.
    """
    gate_blocks = {path.split(".", 1)[0] for path in _REQUIRED_PRESENT}
    for name, node in SCHEMA["properties"].items():
        if not isinstance(node, dict) or name in gate_blocks:
            continue
        required = node.get("required")
        assert not required, f"{name} requires {required}, which the classifier does not read"


def test_every_published_result_still_reads_through_the_current_schema():
    """The promise that makes the corpus worth contributing to.

    Results published under 1.0 and 2.0 must keep reading forever; a schema
    bump that orphans them is a bump that should not have happened.
    """
    from aihwbench.migrations import read_result

    published = sorted(Path("results/published").glob("*.json"))
    assert published
    for path in published:
        doc = json.loads(path.read_text(encoding="utf-8"))
        migrated = read_result(doc)
        assert migrated["schema_version"] == "2.1", path.name
        assert _errors(migrated) == [], f"{path.name}: {_errors(migrated)[:2]}"
