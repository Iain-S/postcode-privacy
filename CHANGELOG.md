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

### Output-changing

- The exponential factors `q**h` are now built from an exact rational bound on `q`,
  each power rounded up from the one before it, instead of being evaluated independently
  with `math.exp` and rounded. The old version let the implemented likelihood ratio
  exceed `exp(epsilon * h)` by about 1e-17 on adversarial priors, which made the stated
  theorem false even though the practical effect was nil
  ([#6](https://github.com/Iain-S/postcode-privacy/issues/6)).
  The requested epsilon is now satisfied exactly. The change alters the total weight the
  keyed draw is taken against, so **every subject's output changes**. Anyone who
  perturbed data with `0.1.0a1` must re-perturb it rather than mixing the two.
