# Community Result Submission Pipeline

How a benchmark result travels from your machine to the public dataset.

```
Benchmark -> Validate -> Sanitize -> Fingerprint -> Submit PR
  -> CI Validation -> Privacy Scan -> Duplicate/Consistency Checks
  -> Maintainer Review -> Publication (trust state applied)
```

## Step by step

1. **Benchmark.** Run with default workload parameters where possible:

   ```bash
   aihwbench benchmark --runtime ollama --model <model-tag>
   # or use a suite profile:
   aihwbench suite smoke --runtime ollama --model <model-tag>
   ```

2. **Validate.**

   ```bash
   aihwbench validate results/raw/<run_id>.json
   ```

3. **Sanitize.** The privacy scanner checks for MAC addresses, IPs,
   serials, tokens, home paths, and usernames. It fails closed — any
   finding blocks submission.

4. **Fingerprint.** Each result carries a deterministic fingerprint of
   its experiment identity; CI uses it to detect accidental duplicates.

5. **Submit a PR** adding:
   - the JSON to `results/published/`
   - a platform note under `platforms/<vendor>/`
   - an updated row in `docs/compatibility-matrix.md` (only for what was
     actually tested)

6. **CI validation.** Every result file is schema-validated on every PR.

7. **Maintainer review.** A maintainer applies a trust state:

   | State | Meaning |
   | --- | --- |
   | `VERIFIED` | Executed/reproduced by the project on real hardware |
   | `COMMUNITY_VALIDATED` | Submitted, validated, reviewed; not independently reproduced |
   | `UNVERIFIED` | Reference only; may contain errors |

## Rules

- Never automatically trust submitted metrics.
- The compatibility matrix only claims what was genuinely tested.
- Sponsored or vendor-provided results are labeled as such.