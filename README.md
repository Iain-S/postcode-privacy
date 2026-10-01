# postcode-privacy

Differential privacy for UK postcodes, measured in **graph hops rather than metres**.

Given a person's real postcode, `postcode-privacy` emits a different *real* postcode such
that the true one is deniable, with a formal guarantee:

> Two postcodes `h` hops apart produce outputs whose likelihoods differ by at most
> `e^(ε·h)`.

Postcode units are joined into a graph where edges link geographic neighbours, so
"one hop" adapts to density automatically — roughly 200 m in central Leeds and roughly
6 km on Bodmin Moor. That is the right behaviour, because the privacy question is
*how many other people could I be?*, not *how many metres away am I?*.

**Status: pre-alpha.** Nothing here is usable yet. See `docs/methods.md` for the formal
statement and proofs, and `docs/superpowers/specs/` for the design of record.

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
