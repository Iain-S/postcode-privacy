# Getting started

!!! warning "Pre-alpha"
    All five commands work and the quickstart runs end to end. The library has not
    been reviewed by anyone but its author, and the known limitations are real — read
    [Limitations](limitations.md) before using it on anything that matters.

## Install

```bash
pip install postcode-privacy
```

With dataframe support for CSV and Parquet input:

```bash
pip install "postcode-privacy[frames]"
```

## 1. Get the data

**The package ships no postcode data, and never will.** Great Britain records in the ONS
Postcode Directory are available under the Open Government Licence, but **Northern
Ireland (`BT`) records are licensed from Land & Property Services and may not be
redistributed**. You build the graph from your own copy.

```bash
# Download the current release automatically (~250 MB).
postcode-privacy build --fetch --uniform-prior -o uk.ppg
```

`--fetch` is best-effort: ONSPD is republished quarterly under a new identifier, and
the portal search that finds it is outside this project's control. Every failure path
tells you how to download by hand and pass `--onspd PATH` instead.

Population figures are a separate download, because the three nations publish them
separately: England and Wales by census output area, Scotland per postcode, Northern
Ireland by data zone. Pass whichever you have; `--oa-populations` and
`--postcode-populations` are both repeatable.

```bash
postcode-privacy build \
    --onspd ONSPD_AUG_2026_UK.csv \
    --oa-populations census2021_oa_population_ew.csv \
    --oa-populations ni_census2021_datazone_population.csv \
    --oa-populations scotland_outputarea2022_usualresidentpopulation.csv \
    --postcode-populations scotland_postcode2022_usualresidentpopulation.csv \
    -o uk.ppg
```

```
read 2,729,090 rows -> 1,725,511 usable nodes
  dropped large user: 75,253
  dropped no grid reference: 9,600
  dropped terminated: 918,726
prior: population, 66,305,212 people. coverage 100.00%
  (per postcode 152,485, per area 1,573,026, floored 0)
graph: 5,357,722 edges, mean degree 6.21
```

Coverage is reported rather than assumed. A prior that had silently fallen back to its
floor across a whole nation would otherwise look exactly like a working one, which is
also why **a uniform prior has to be asked for explicitly** with `--uniform-prior`
rather than being a silent fallback.

A build manifest is written beside the artefact, recording the source file and its
SHA-256, every exclusion count, and where each postcode's weight came from.

If you intend to share the resulting artefact, exclude Northern Ireland:

```bash
postcode-privacy build --onspd ONSPD_AUG_2026_UK.csv --gb-only -o gb.ppg
```

## 2. Make a key

Perturbation is keyed and deterministic, so the same person always maps to the same
output. That is what stops repeated releases from leaking more than one.

```bash
postcode-privacy keygen -o secret.key
```

The file is created mode `0400` — readable only by you, and never briefly wider than
that. `keygen` refuses to overwrite an existing key, because replacing one orphans every
release made with the old key: those outputs can never be reproduced or explained again.

!!! danger "The key is as sensitive as the raw data"
    Anyone holding both the key and the graph can invert the perturbation exactly and
    recover every true postcode. Store it as you would store the source dataset — not in
    the repository, not in a shared drive, not in your shell history.

    The CLI will not accept a key as an argument value for this reason. Only
    `--key-file` or the `POSTCODE_PRIVACY_KEY` environment variable are permitted.

## 3. Perturb a dataset

CSV needs no extra. Parquet needs `postcode-privacy[frames]`, and the format is
chosen per file, so a pipeline can change format and perturb in one step.

```bash
postcode-privacy perturb patients.csv -o patients_dp.csv \
    --graph uk.ppg \
    --epsilon 0.8 \
    --postcode-col postcode \
    --subject-col patient_id \
    --key-file secret.key
```

Every run prints the privacy parameters actually used to stderr, so they end up in your
pipeline logs rather than being invisible:

```
graph: ONSPD_AUG_2026_UK.csv
epsilon: 1.0 per hop   radius: 62 hops
max teleport probability: 2.2e-09
rows: 4 in, 4 written, 0 failed
wrote patients_dp.csv and patients_dp.manifest.json
```

### The manifest

Alongside the output, `perturb` always writes a JSON manifest recording the graph and
its source hash, the epsilon and radius used, the highest teleport probability any
record was exposed to, the error policy, and the row counts. Standard error gets lost;
a file does not, and this is what makes a release auditable and reproducible afterwards.

### Diagnostics name rows, never postcodes

If a record cannot be perturbed, the error identifies it by row number:

```
Error: 2 row(s) could not be perturbed: row 1, 3. Postcodes are not shown, so that
source data does not reach the logs; look the rows up in the input.
```

This is deliberate. Naming the offending value would copy real postcodes out of the
dataset and into pipeline logs, which are usually less well protected than the data
they describe. `--on-error drop` removes such rows, `--on-error null` keeps them with an
empty output, and both are recorded in the manifest. A run that dropped or nulled rows
exits with status 3, so a pipeline can branch on it without parsing text.

The `--subject-col` is required, not optional. Without a stable subject identifier the
mechanism cannot keep a person's output consistent, and repeated releases would degrade
the guarantee.

## 4. Choose an epsilon

\(\varepsilon\) is a rate per hop, and nobody has intuition for it. Rather than guessing,
state the utility you need and solve for it:

```bash
postcode-privacy calibrate --graph uk.ppg --target median-displacement-km=2.0
```

Or inspect what a given \(\varepsilon\) does, nationally or to one postcode:

```bash
postcode-privacy report --graph uk.ppg --epsilon 1.0 --postcode "LS6 1AA"
postcode-privacy report --graph uk.ppg --epsilon 1.0 --sample 100 --json
```

```
LS6 1AA at epsilon 1.0 per hop, radius 62 hops
  displacement: median 0.38 km, p95 1.03 km, mean 0.55 km
  self probability: 4.200% (chance the true postcode is handed back)
  teleport probability: 2.2e-09
  ball size: 46,694 postcodes
  displacement excludes teleports, which are counted separately.
```

Displacement is reported **conditional on not teleporting**, with the teleport
probability beside it. Combining them would hide a radius that is too small, because a
handful of country-wide jumps would drag the average up and look like ordinary local
spread.

### What epsilon buys, measured

Over 15 sampled postcodes per group on the August 2026 build:

| ε | radius | urban median | same LSOA | rural median | same LSOA |
|---|---|---|---|---|---|
| 0.3 | 200 hops | 2.60 km | 2.9% | 23.24 km | 1.7% |
| 0.5 | 122 hops | 1.49 km | 8.8% | 10.22 km | 4.8% |
| 1.0 | 62 hops | 0.48 km | 24.7% | 4.31 km | 16.4% |
| 2.0 | 32 hops | 0.21 km | 54.8% | 1.95 km | 43.7% |

"Same LSOA" is the share of output probability that stays in the true postcode's census
output area — the practical question of whether you can still count people by geography.
At \(\varepsilon = 0.3\) almost none of it does, which is the number to weigh before
choosing a small \(\varepsilon\) for safety's sake.

!!! note "Calibration is slow, deliberately"
    Solving a displacement target costs roughly eighteen seconds per sampled postcode
    on a national graph, because every candidate \(\varepsilon\) implies a different
    radius and so a different ball. The default sample is 16; raising it raises the
    cost proportionally. Progress is printed to standard error.

## From Python

```python
from postcode_privacy import PostcodeGraph, HopMechanism, Key

graph = PostcodeGraph.load("uk.ppg")
key = Key.from_env("POSTCODE_PRIVACY_KEY")
mechanism = HopMechanism(graph, epsilon=0.8, prior="population")

mechanism.perturb("LS2 9JT", subject_id="patient-0041", key=key)
# -> 'LS6 1AA'

# The exact output distribution, not a sample of it -- this is the auditable object.
mechanism.distribution("LS2 9JT")
```
