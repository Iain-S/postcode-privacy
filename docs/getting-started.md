# Getting started

!!! warning "Pre-alpha"
    None of this runs yet. It documents the intended interface so that it can be argued
    with before it is built.

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
# Fetch the current ONSPD release from the ONS Open Geography Portal (~250 MB).
postcode-privacy build --fetch -o uk.ppg

# Or point at a download you already have.
postcode-privacy build --onspd ONSPD_AUG_2026_UK.csv -o uk.ppg
```

For a population-weighted prior, supply census population figures as well. Without
them the prior falls back to uniform, with a warning rather than an error.

```bash
postcode-privacy build \
    --onspd ONSPD_AUG_2026_UK.csv \
    --oa-populations census2021_oa_population_ew.csv \
    -o uk.ppg
```

If you intend to share the resulting artefact, exclude Northern Ireland:

```bash
postcode-privacy build --onspd ONSPD_AUG_2026_UK.csv --gb-only -o gb.ppg
```

## 2. Make a key

Perturbation is keyed and deterministic, so the same person always maps to the same
output. That is what stops repeated releases from leaking more than one.

```bash
postcode-privacy keygen -o secret.key
chmod 600 secret.key
```

!!! danger "The key is as sensitive as the raw data"
    Anyone holding both the key and the graph can invert the perturbation exactly and
    recover every true postcode. Store it as you would store the source dataset — not in
    the repository, not in a shared drive, not in your shell history.

    The CLI will not accept a key as an argument value for this reason. Only
    `--key-file` or the `POSTCODE_PRIVACY_KEY` environment variable are permitted.

## 3. Perturb a dataset

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
graph: uk.ppg (ONSPD_AUG_2026, 1,714,392 live postcodes)
epsilon: 0.8 per hop   radius: 60 hops   teleport probability: 4.1e-07
prior: population      subjects: 48,210  distinct postcodes: 31,884
```

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
postcode-privacy report --graph uk.ppg --epsilon 0.8 --sample 10000
postcode-privacy report --graph uk.ppg --epsilon 0.8 --postcode "LS2 9JT"
```

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
