# Minting the dataset DOI

Everything for this is prepared except the step that needs the maintainer's
account. This page is the runbook, so the DOI is minted deliberately rather
than reconstructed from memory later.

## What the DOI is for

It covers a **dataset snapshot**, not the tool. A citation has to resolve to an
exact set of measurements; one that resolved to "whatever the repository holds
today" would let the cited numbers change after publication, which is the
failure a DOI exists to prevent.

`aihwbench snapshot` produces the snapshot and records each result's hash, so
the archived artifact and the repository can be checked against each other.

## Before minting

The dataset should span more than one hardware class. A DOI on a single-laptop
corpus invites citation as though it were representative, and it is not — the
whole argument of this project is that hardware differs and the differences are
what matter.

Concretely, wait until published results cover at least three distinct GPU or
SoC classes.

## Steps

1. Check the corpus is ready:

   ```bash
   aihwbench snapshot --version v1 --results-dir results/published
   aihwbench quality results/published
   ```

   Every result must pass the data-quality checks, including
   `measured_on_an_idle_machine`.

2. Log in to [Zenodo](https://zenodo.org) with the GitHub account that owns the
   repository, and enable the repository under *Settings → GitHub*.

3. Publish a GitHub release. Zenodo archives the tagged tree and mints the DOI
   from `.zenodo.json`, which is already in the repository root.

4. Record the DOI:

   - `CITATION.cff` — add the `doi:` field.
   - `docs/research/citation.md` — replace the "no DOI exists today" note.
   - `README.md` — add the badge.

   `tests/test_doi_consistency.py` checks these three agree, so a DOI recorded
   in one place and not the others fails the suite.

## What not to do

**Do not mint a DOI per release.** Zenodo offers a concept DOI covering all
versions and a version DOI for each. Cite the version DOI in papers, because a
concept DOI resolves to the newest snapshot and reintroduces exactly the
mutability the DOI was meant to remove.
