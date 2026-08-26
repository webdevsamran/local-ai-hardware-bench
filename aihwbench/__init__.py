"""Open Local AI Hardware Benchmark & Compatibility Initiative.

A vendor-neutral framework for benchmarking local AI runtimes across
CPUs, GPUs, NPUs, AI PCs, workstations, mini PCs, and edge accelerators.
"""

__version__ = "0.1.0"

SCHEMA_VERSION = "1.0"

# Benchmark protocol version: identifies the measurement methodology
# (workload definitions, aggregation rules, telemetry policy).
# Bumped independently of the package version and result schema.
PROTOCOL_VERSION = "1"
