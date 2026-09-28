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
