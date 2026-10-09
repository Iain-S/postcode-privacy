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

### Output stability is part of the version number

A given subject always receives the same perturbed postcode — that is the promise that
makes repeated publication safe. Anything changing node ordering, the keyed function,
the prior, the graph or the arithmetic re-perturbs everyone, so it is versioned:

- **patch** (`0.1.0` → `0.1.1`): outputs identical for every subject
- **minor** (`0.1.x` → `0.2.0`): outputs may change, listed in
  [CHANGELOG.md](https://github.com/Iain-S/postcode-privacy/blob/main/CHANGELOG.md)

Pin `postcode-privacy == 0.1.*` to keep outputs fixed. If you have released perturbed
data, **keep the `.ppg` artefact** and record the library version and the manifest's
`graph_sha256`, which identifies that artefact exactly. The ONSPD hash alone is not
enough: two graphs built from one ONSPD with different population inputs give every
subject a different output. Rebuilding an identical graph from source inputs is a
separate and weaker proposition — see
[Reproducing a release](https://iain-s.github.io/postcode-privacy/getting-started/#reproducing-a-release-and-rebuilding-a-graph).

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
postcodes**. Full attribution is in [References](https://iain-s.github.io/postcode-privacy/references/).

## Data and licensing

This package **ships no postcode data**. You build a graph artefact from your own copy
of the ONS Postcode Directory. Great Britain postcodes in ONSPD are available under the
Open Government Licence; **Northern Ireland (`BT`) postcodes carry a restrictive Land &
Property Services end-user licence and may not be redistributed.**

## Keys are as sensitive as the raw data

Perturbation is keyed and deterministic, so the same person always maps to the same
output. That makes repeated publication safe, and it also means the guarantee is
**computational**: the randomness is over a uniformly drawn secret key, with
HMAC-SHA256 assumed to be a pseudorandom function.

Anyone holding both the key and the graph can evaluate the mechanism themselves and
eliminate every postcode that does not map to the observed output, leaving a handful of
candidates at most. Treat key compromise as disclosure of the source postcodes, and the
key itself with the same care as the source dataset. Rotating it re-perturbs everyone,
so rotation is a privacy cost rather than hygiene.

The full statement — the PRF experiment, the conditions under which repeated releases
count as one observation, subject-identifier requirements, and where this sits against
the ICO's guidance on differential privacy — is in
[Threat model](https://iain-s.github.io/postcode-privacy/threat-model/).

## Licence

MIT.
