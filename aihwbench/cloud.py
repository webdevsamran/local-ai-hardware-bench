"""Cloud instance profiles, as a baseline to compare owning hardware against.

Specs are bundled; prices are not, and the split is deliberate.

A named instance type's hardware is a stable fact: a `g5.xlarge` has an A10G
with 24 GB, and it had one last year. Its *price* changes with the region, the
commitment, the spot market and the week, so a price table inside a benchmark
would go stale quietly and keep producing confident wrong answers -- which is
the reason `analysis.cost` already requires the caller to supply one.

So each profile carries what the machine is, and the caller supplies what they
were quoted. Every profile records where its specs were read and when, the same
way `configs/models.json` records where a licence was read: an uncited spec is
an assertion, and one with a URL and a date is a claim someone can check.

These exist to answer "is owning this worth it", not to rank cloud providers.
This project has measured none of these instances, and a profile is not a
result.
"""

from __future__ import annotations

from typing import Any

__all__ = ["CLOUD_PROFILES", "get_profile", "list_profiles", "compare_against_profile"]

#: Instance hardware, as published by each vendor on the date stated.
#:
#: Deliberately short. A long table is a long list of things that can rot, and
#: the point is a credible baseline rather than a directory.
CLOUD_PROFILES: dict[str, dict[str, Any]] = {
    "aws-g5-xlarge": {
        "provider": "AWS",
        "instance": "g5.xlarge",
        "gpu": "NVIDIA A10G",
        "gpu_count": 1,
        "gpu_vram_mb": 24576,
        "vcpu": 4,
        "ram_gb": 16,
        "source": "https://aws.amazon.com/ec2/instance-types/g5/",
        "specs_read_on": "2026-09-11",
    },
    "aws-g6-xlarge": {
        "provider": "AWS",
        "instance": "g6.xlarge",
        "gpu": "NVIDIA L4",
        "gpu_count": 1,
        "gpu_vram_mb": 24576,
        "vcpu": 4,
        "ram_gb": 16,
        "source": "https://aws.amazon.com/ec2/instance-types/g6/",
        "specs_read_on": "2026-09-11",
    },
    "gcp-g2-standard-4": {
        "provider": "Google Cloud",
        "instance": "g2-standard-4",
        "gpu": "NVIDIA L4",
        "gpu_count": 1,
        "gpu_vram_mb": 24576,
        "vcpu": 4,
        "ram_gb": 16,
        "source": "https://cloud.google.com/compute/docs/gpus",
        "specs_read_on": "2026-09-11",
    },
    "azure-nc4as-t4-v3": {
        "provider": "Azure",
        "instance": "Standard_NC4as_T4_v3",
        "gpu": "NVIDIA T4",
        "gpu_count": 1,
        "gpu_vram_mb": 16384,
        "vcpu": 4,
        "ram_gb": 28,
        "source": "https://learn.microsoft.com/azure/virtual-machines/nct4-v3-series",
        "specs_read_on": "2026-09-11",
    },
}


def list_profiles() -> list[str]:
    return sorted(CLOUD_PROFILES)


def get_profile(key: str) -> dict[str, Any]:
    try:
        return dict(CLOUD_PROFILES[key])
    except KeyError:
        known = ", ".join(list_profiles())
        raise KeyError(f"unknown cloud profile {key!r}; known: {known}") from None


def compare_against_profile(
    profile_key: str,
    hourly_usd: float | None,
    local_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Set a local measurement beside a rented machine of stated specs.

    The hourly rate is required and never defaulted, for the reason the module
    docstring gives. Without one this still returns the profile, because
    knowing what you would be renting is useful before knowing what it costs.

    What this deliberately does not do is claim a throughput for the cloud
    instance. Nobody has measured these here, and a comparison of a measured
    local number against an assumed remote one is not a comparison -- it is the
    assumption, dressed up.
    """
    profile = get_profile(profile_key)
    metrics = (local_result or {}).get("metrics") or {}
    system = (local_result or {}).get("system") or {}

    report: dict[str, Any] = {
        "profile": profile,
        "hourly_usd": hourly_usd,
        "local": {
            "gpu": system.get("gpu"),
            "gpu_vram_mb": system.get("gpu_vram_mb"),
            "generation_tokens_per_second": metrics.get("generation_tokens_per_second"),
        },
        "cloud_throughput": None,
        "note": (
            "no throughput is given for the cloud instance: this project has "
            "not measured one. The comparison this supports is 'would the model "
            "fit, and what would the hardware cost', not 'which is faster'."
        ),
    }

    local_vram = system.get("gpu_vram_mb")
    if isinstance(local_vram, int | float) and local_vram > 0:
        report["vram_ratio_local_over_cloud"] = round(
            float(local_vram) / float(profile["gpu_vram_mb"]), 3
        )

    if hourly_usd is None or hourly_usd <= 0:
        report["unresolved"] = (
            "no hourly rate supplied. Instance pricing varies by region, "
            "commitment and the spot market, so this project does not carry a "
            "price table: use the figure you were quoted."
        )
        return report

    hours_per_year = 24 * 365
    report["annual_usd_if_always_on"] = round(float(hourly_usd) * hours_per_year, 2)
    report["unresolved"] = None
    return report
