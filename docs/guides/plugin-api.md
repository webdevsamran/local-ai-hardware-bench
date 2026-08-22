# Backend Plugin API (v1)

AIHWBench supports two ways to add a runtime backend:

1. **Built-in**: add a module under `benchmark/backends/` and register
   it in `benchmark/backends/__init__.py`.
2. **External plugin** (recommended for third parties): publish a Python
   package that registers an entry point in the `aihwbench.backends`
   group. No changes to this repository are required.

## Entry point registration

In your package's `pyproject.toml`:

```toml
[project.entry-points."aihwbench.backends"]
myruntime = "my_package.backend"
```

The entry point value must resolve to a **module** exposing:

- `detect() -> BackendInfo`
- `run(config: BenchmarkConfig, system: dict) -> dict`

## Contract

| Rule | Detail |
| --- | --- |
| `detect()` never raises | Return a `BackendInfo` with an appropriate `RuntimeStatus`. Any exception is caught by the registry and reported as `NOT_AVAILABLE`. |
| `run()` fails cleanly | Raise `BackendError` with an actionable message when prerequisites are missing (no runtime, no model, no driver, insufficient VRAM). Never fabricate metrics. |
| Result documents | Must validate against schema 1.0 (`benchmark.schemas.validate_result`). Unavailable metrics are `null`, never estimated. |
| Metadata | Optionally expose a module-level `METADATA: BenchmarkMetadata` describing capabilities. |
| API version | Target `BACKEND_API_VERSION = 1`. Breaking registry changes bump this constant. |

## Statuses

Use `RuntimeStatus` honestly:

- `AVAILABLE` — installed and usable right now.
- `NOT_INSTALLED` / `CONFIGURATION_REQUIRED` — actionable detail string.
- `HARDWARE_REQUIRED` — runtime exists but needs hardware we don't have.
- `UNSUPPORTED_PLATFORM`.

## Testing requirements

A backend PR must include tests that verify:

1. `detect()` on a machine without the runtime returns a clean status.
2. `run()` raises `BackendError` cleanly when prerequisites are missing.
3. If you can run it locally: a schema-valid result document.

Simulated/mocked hardware tests are fine for logic, but a backend may
only be marked "Tested" in the compatibility matrix after a real
execution on real hardware.