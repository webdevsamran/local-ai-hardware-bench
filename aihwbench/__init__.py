"""Open Local AI Hardware Benchmark & Compatibility Initiative.

A vendor-neutral framework for benchmarking local AI runtimes across
CPUs, GPUs, NPUs, AI PCs, workstations, mini PCs, and edge accelerators.
"""

from aihwbench.versions import (
    CURRENT_SCHEMA_VERSION,
    PACKAGE_VERSION,
    PROTOCOL_VERSION,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
)

__version__ = PACKAGE_VERSION

__all__ = [
    "__version__",
    "PACKAGE_VERSION",
    "SCHEMA_VERSION",
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "PROTOCOL_VERSION",
]
