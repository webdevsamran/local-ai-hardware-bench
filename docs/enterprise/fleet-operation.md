# Fleet benchmarking — design (Planned / Future)

> **Status: planned.** No orchestrator exists in this repository. This page
> records the design decisions, and in particular the one that makes fleet
> benchmarking harder than it looks.

## The problem nobody expects

Running the same benchmark on fifty machines is easy. The core is a CLI, it is
offline, it writes JSON; a shell loop and a shared directory will do it.

What is hard is what comes back. Fifty heterogeneous machines produce results
that **mostly cannot be compared with each other**, and the obvious dashboard —
one leaderboard, fifty rows, sorted by tokens per second — is wrong in a way
that looks authoritative. Different drivers, different quantizations, different
power profiles, half of them on battery. The comparison-safety classifier
exists precisely because that table is a lie, and a fleet is the fastest way to
produce fifty rows of it.

So the design below is mostly about comparability, not about scheduling.

## Shape

```
Runner (this repo, unchanged)  -> result JSON
        ...                    -> result JSON      [N machines]
                                      |
                               Collector           [planned]
                                      |
                            Private store          [planned, see storage-adapter.md]
                                      |
                       Grouping + policy engine    [planned]
```

The runner does not change. A machine in a fleet runs the same command a person
runs, which is what makes a fleet result reproducible by hand — the property
that would be lost first if orchestration reached into the measurement.

## Decisions

### The fleet does not rank; it groups

The collector must apply `export.comparison_groups` before anything is
displayed. That function partitions results into mutually-comparable cliques,
checking each candidate against *every* member rather than a representative,
because comparability is not transitive.

A fleet view is therefore *n* small leaderboards, not one large one. Most groups
will have a single member, and a group of one cannot be ranked. That is the
honest rendering, and it is also the useful one: it shows immediately that
fifty machines produced two comparable pairs, which is the actual state of the
estate.

### Heterogeneity is the finding, not the noise

The temptation is to normalise — same model, same flags, same everything — so
the numbers line up. That produces a tidy table describing a fleet nobody has.

The useful fleet run is the opposite: every machine as it is actually
configured, with the classifier reporting what that costs. "Thirty-one of fifty
machines cannot be compared with any other because their driver versions differ"
is a finding about fleet management, and no throughput number is worth more than
it.

### Contention is per-machine and must be recorded per-machine

The core already samples CPU and GPU load before a run and refuses to publish
above a threshold. In a fleet this stops being a warning and becomes the main
source of error: machines are someone's desktop, and a scheduled overnight
sweep hits backup windows and antivirus scans.

Every fleet result carries its own contention sample. The collector must not
aggregate across machines without it — an average over fifty machines of which
nine were busy is an average of the wrong population.

### Scheduling is the caller's

No scheduler in this repository. `cron`, a CI matrix, or an existing fleet tool
already does this better, and the value here is the measurement and the
comparability rules, not another job runner. The collector accepts results; it
does not dispatch work.

### Failures are results

A machine that could not run the benchmark reports why, in the same pipeline.
The CLI's stable exit codes already carry the distinction — configuration
missing, hardware absent, not comparable, regression detected — and a fleet view
that shows only successes will quietly stop covering the machines that break
most often.

## What the open core still owes this

- No collector, and no reference one.
- `comparison_groups` is O(n²) in comparisons per group. Fine for the published
  dataset; unmeasured at fleet size, and it should be measured before anyone
  builds on it.
- Contention sampling is recorded per result but there is no aggregate over a
  set of results, so "how much of this sweep is trustworthy" has no answer yet.

## What this design refuses

A fleet dashboard showing one number per machine, sorted. It is what everybody
wants, it is what the tooling makes easy, and it is the thing this project
exists to argue against. If the fleet view cannot show which machines are
comparable with which, it should show nothing.
