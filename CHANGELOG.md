# Changelog

## Output stability is part of the version number

This library's central promise is that a given subject always receives the same
perturbed postcode. Anything that changes node ordering, the keyed function, the
population prior, the graph construction or the arithmetic **re-perturbs everyone**, and
two releases of the same people made either side of such a change leak more than one —
which is precisely what the design exists to prevent.

So output stability is versioned:

| change | outputs may change? |
|---|---|
| patch release, `0.1.0` → `0.1.1` | **no** — identical for every subject |
| minor release, `0.1.x` → `0.2.0` | yes, and it will be listed below under **Output-changing** |
| major release | yes |

If you have released perturbed data, record the version and the graph artefact's
`source_sha256` from its manifest. Reproducing that release later needs both.

Pinning `postcode-privacy == 0.1.*` keeps outputs fixed.

---

## Unreleased

First packaged release. Pre-alpha: the implementation has not been reviewed by anyone
outside the repository.
