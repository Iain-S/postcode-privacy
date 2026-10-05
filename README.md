# postcode-privacy

Differential privacy for UK postcodes, measured in **graph hops rather than metres**.

Given a person's real postcode, `postcode-privacy` emits a different *real* postcode such
that the true one is deniable, with a formal guarantee:

> Two postcodes `h` hops apart produce outputs whose likelihoods differ by at most
> `e^(ε·h)`.

Postcode units are joined into a graph where edges link geographic neighbours, so
"one hop" adapts to density automatically. Measured on the August 2026 build, six hops
spans about **two kilometres** in inner Leeds and about **160 kilometres** in Sutherland,
while reaching a comparable number of people in each. That is the right behaviour,
because the privacy question is *how many other people could I be?*, not *how many
metres away am I?*.

**Documentation: <https://iain-s.github.io/postcode-privacy/>**

## Status

**Pre-alpha, but it works.** All six commands run, and the quickstart goes end to end
against a real ONS Postcode Directory: a national graph of 1,725,511 postcodes builds in
under a minute, and perturbing a million rows takes twelve seconds.

```bash
postcode-privacy build      # ONSPD in, graph artefact out
postcode-privacy keygen     # a secret key
postcode-privacy perturb    # CSV or Parquet in, perturbed postcodes out
postcode-privacy report     # what an epsilon does, before you release anything
postcode-privacy calibrate  # solve for the epsilon meeting a target
postcode-privacy evaluate   # utility by urban/rural group
```

What *pre-alpha* means here, specifically:

- **Not on PyPI.** Install from this repository (see below).
- **No external review.** There are 308 tests, mutation checks, and golden determinism
  tests running on two operating systems, but nobody outside this repository has
  audited it, and a privacy guarantee is a property of an implementation as much as of a
  theorem.
- **The known limitations are real.** Read
  [Limitations](https://iain-s.github.io/postcode-privacy/limitations/) before using it
  on anything that matters.

The design of record is in `docs/superpowers/specs/`; the formal statement and proofs
are in [Methods](https://iain-s.github.io/postcode-privacy/methods/).

## Install

```bash
pip install "postcode-privacy @ git+https://github.com/Iain-S/postcode-privacy"
```

Add the `frames` extra for Parquet support:

```bash
pip install "postcode-privacy[frames] @ git+https://github.com/Iain-S/postcode-privacy"
```

## Credit

The central idea here is not ours. Measuring metric differential privacy by
shortest-path distance on a graph, rather than by Euclidean distance, is
**Geo-Graph-Indistinguishability**, due to Shun Takagi, Yang Cao, Yasuhito Asano and
Masatoshi Yoshikawa ([arXiv:2010.13449](https://arxiv.org/abs/2010.13449); DBSec 2019),
who also give the Graph-Exponential Mechanism. It rests in turn on metric differential
privacy (Chatzikokolakis et al., PETS 2013) and geo-indistinguishability (Andrés et al.,
CCS 2013).

What this library adds is narrow: UK postcode units as the secret space, a
population-weighted prior, an exactly-computable capped metric, keyed-deterministic
perturbation, and integer weights. In one sentence, it is **GG-I applied to UK
postcodes**. Full attribution is in [`docs/references.md`](docs/references.md).

## Data and licensing

This package **ships no postcode data**. You build a graph artefact from your own copy
of the ONS Postcode Directory. Great Britain postcodes in ONSPD are available under the
Open Government Licence; **Northern Ireland (`BT`) postcodes carry a restrictive Land &
Property Services end-user licence and may not be redistributed.**

## Keys are as sensitive as the raw data

Perturbation is keyed and deterministic, so the same person always maps to the same
output. Anyone holding both the key and the graph can invert it exactly. Treat the key
with the same care as the source dataset.

## Licence

MIT.
