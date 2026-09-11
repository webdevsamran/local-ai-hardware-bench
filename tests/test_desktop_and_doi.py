"""The desktop scaffold and the DOI runbook: prepared, and honest about it.

Neither is finished on the reference machine, and each is unfinished for a
different reason that the tests state rather than imply.

The desktop app is **not compiled here**. Rust 1.98.1 is installed and
`link.exe` fails because the Visual Studio "C++ build tools" workload is
absent. What is checked is that the configuration parses, that its paths
resolve to real things, and that the Rust source shells out rather than
reimplementing the benchmark. A valid config is not a working binary and these
tests do not pretend otherwise.

The DOI is **not minted**, because minting one requires the maintainer's Zenodo
account. What is checked is that the metadata Zenodo will read is valid and
agrees with the repository.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

TAURI_CONF = Path("desktop/src-tauri/tauri.conf.json")
CARGO_TOML = Path("desktop/src-tauri/Cargo.toml")
MAIN_RS = Path("desktop/src-tauri/src/main.rs")
ZENODO = Path(".zenodo.json")


# --- desktop scaffold -------------------------------------------------------


def test_the_tauri_config_is_valid_json():
    json.loads(TAURI_CONF.read_text(encoding="utf-8"))


def test_the_frontend_points_at_the_real_dashboard_build():
    """Not a second copy of the UI.

    A desktop app with its own frontend would drift from the site, and the two
    would disagree about the same data.
    """
    config = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    frontend = config["build"]["frontendDist"]
    resolved = (TAURI_CONF.parent / frontend).resolve()
    assert resolved == Path("web/dist").resolve()


def test_the_version_matches_the_package():
    """A desktop build claiming a different version than the CLI it wraps
    would make a bug report unattributable."""
    from aihwbench.versions import PACKAGE_VERSION

    config = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    assert config["version"] == PACKAGE_VERSION
    assert f'version = "{PACKAGE_VERSION}"' in CARGO_TOML.read_text(encoding="utf-8")


def test_the_gui_shells_out_rather_than_reimplementing_anything():
    """The one design rule.

    A GUI that computed its own metrics would be a second implementation of
    the benchmark, drifting in the direction nobody checks -- because the GUI
    is what people use and the CLI is what has tests.
    """
    source = MAIN_RS.read_text(encoding="utf-8")
    assert 'Command::new("aihwbench")' in source
    for forbidden in ("tokens_per_second", "peak_vram", "acceptance_rate"):
        assert forbidden not in source, (
            f"main.rs mentions {forbidden}: the shell must not compute metrics"
        )


def test_the_ui_cannot_run_arbitrary_subcommands():
    """A text field wired to a subprocess is an execution hole."""
    source = MAIN_RS.read_text(encoding="utf-8")
    assert "ALLOWED_SUBCOMMANDS" in source
    assert "is not exposed to the UI" in source


def test_the_command_that_ran_is_returned_to_the_caller():
    """A GUI that hides its command produces results nobody can reproduce by
    hand, which defeats the point of a benchmark."""
    assert "command," in MAIN_RS.read_text(encoding="utf-8")


def test_the_readme_says_it_has_not_been_built_here():
    """Claiming a working binary would be the one dishonest thing available."""
    readme = Path("desktop/README.md").read_text(encoding="utf-8")
    assert "Not built or run on the reference machine" in readme
    assert "C++ build tools" in readme


# --- DOI --------------------------------------------------------------------


def test_the_zenodo_metadata_is_valid_and_complete():
    metadata = json.loads(ZENODO.read_text(encoding="utf-8"))
    for field in ("title", "description", "upload_type", "license", "creators"):
        assert metadata.get(field), f"Zenodo needs {field}"


def test_the_doi_covers_a_snapshot_rather_than_the_repository():
    """A citation resolving to "whatever is there today" lets the cited
    numbers change after publication, which is what a DOI prevents."""
    metadata = json.loads(ZENODO.read_text(encoding="utf-8"))
    assert "snapshot" in metadata["notes"].lower()


def test_the_licence_matches_the_repository():
    metadata = json.loads(ZENODO.read_text(encoding="utf-8"))
    licence = Path("LICENSE").read_text(encoding="utf-8")
    assert metadata["license"].lower().startswith("apache")
    assert "Apache License" in licence


def test_no_doi_is_claimed_anywhere_until_one_is_minted():
    """The failure this guards is a placeholder DOI escaping into a citation.

    An unregistered DOI in CITATION.cff would be copied into a bibliography
    and resolve to nothing.
    """
    doi_pattern = re.compile(r"10\.5281/zenodo\.\d+")
    for path in (Path("CITATION.cff"), Path("docs/research/citation.md"), Path("README.md")):
        if not path.is_file():
            continue
        assert not doi_pattern.search(path.read_text(encoding="utf-8")), (
            f"{path} names a DOI; if one has been minted, update the runbook and this test together"
        )


def test_the_runbook_exists_and_names_the_preconditions():
    runbook = Path("docs/research/minting-a-doi.md")
    assert runbook.is_file()
    text = runbook.read_text(encoding="utf-8")
    # The precondition that matters: a one-laptop corpus cited as
    # representative is the failure a premature DOI causes.
    assert "hardware class" in text
    assert "version DOI" in text


@pytest.mark.parametrize("path", [TAURI_CONF, CARGO_TOML, MAIN_RS, ZENODO])
def test_the_prepared_files_are_tracked(path):
    """Scaffolding that is gitignored helps nobody."""
    import subprocess

    listed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)], capture_output=True, text=True
    )
    assert listed.returncode == 0, f"{path} is not tracked by git"
