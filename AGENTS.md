# Working on postcode-privacy

Things that are not obvious from reading the code or the docs. Read this before changing
anything; several of the decisions below look like bugs or oversights and are not.

> **Keep this file current.** If you change a default, a guarantee, a guard, or any of the
> decisions recorded here, update this file in the same commit. A stale AGENTS.md is worse
> than none, because the next agent will trust it.

## Things that look wrong but are deliberate

**Pruning and bridging are off by default. Do not enable them to "fix" the graph.**
`assemble()` returns the unmodified Delaunay triangulation. The pruning heuristic exists,
is tested, and is opt-in via `prune_alpha`. It is off because no geometric criterion can
separate an estuary from an empty moor — in a point set they are the same object, a gap
with nothing in it. Length thresholds cannot do it and neither can Gabriel or
relative-neighbourhood graphs. The information is not in the data. The real fix is road or
hydrography data, deferred to a future version.

**Bridging is not needed on the default path.** Raw Delaunay triangulates the convex hull,
so every point is already connected — an island far offshore included. Bridging exists
*only* to repair what pruning severs, and is enabled with it. There is a test asserting
this; do not add bridging to the unpruned path.

**The radius cap applies to the metric, not the support.** The mechanism uses
`min(d, R)`, so every postcode in the country keeps nonzero probability and the
out-of-ball mass is computed in closed form. The obvious optimisation — BFS to radius `R`
and renormalise over that ball — **breaks pure differential privacy**, because a node
inside `x`'s ball but outside `x'`'s gets probability zero under one and not the other,
making the likelihood ratio unbounded. This is mutation-tested. Do not "simplify" it.

**Weights are integers, not floats.** Two independent reasons: floating-point DP
implementations leak the true input through low bits of the IEEE representation (Mironov,
CCS 2012), and the promise that a subject's output never changes would otherwise depend on
summation order, NumPy version and platform. Do not convert to float for convenience.

**Node ordering is canonical, sorted by normalised postcode.** Node indices derive from it
and keyed determinism derives from node indices. Reordering nodes silently changes every
subject's output. Postcode normalisation is part of the privacy contract, not a
convenience.

**`_reference.py` is deliberately slow and naive.** It is the oracle the optimised code is
differentially tested against: dense Floyd-Warshall, full enumeration, no caching. Its
value is being too simple to be wrong. Do not optimise it, and never import it from
library code.

## Data handling — this is a licensing matter, not tidiness

ONSPD's **Northern Ireland (`BT`) records are licensed from Land & Property Services and
may not be redistributed.** Great Britain records are Open Government Licence.

Consequences, all enforced:

- The package ships **no** postcode data, ever. A CI job asserts the built wheel contains
  no data files.
- Source data and graph artefacts are gitignored by name *and* by directory, so a copy
  made outside `data/` is still caught.
- A local pre-commit hook refuses to commit anything named `ONSPD*`, `NSPL*` or `*.ppg`.
  This exists because `.gitignore` can be bypassed with `git add -f`. **Do not remove or
  skip this hook.**
- `--gb-only` exists so that a shareable artefact can be built. Use it for anything
  intended to leave the machine it was built on.

## Known traps

**ONSPD column names change between releases.** The August 2026 release uses
`east1m`/`north1m`, not the `oseast1m`/`osnrth1m` of earlier ones; also `oa21cd`,
`lsoa21cd`, `msoa21cd`, `lad26cd`, `ruc21ind`, `usrtypind`, `gridind`. Values are quoted.
The reader validates the header and raises `OnspdSchemaError` rather than reading on,
because a renamed column otherwise makes every row fail the grid-reference test and an
unreadable file looks exactly like an empty country. If a new release renames something,
update the constants at the top of `graph/onspd.py`.

**Test fixtures encoded the wrong column names for a while and the suite passed.** That
is the failure mode to watch for in this repository: fixtures that confirm an assumption
instead of checking reality. Verify parsers against the real file, not only fixtures.

**A radius that is too small is a silent utility disaster.** It does not error; it quietly
raises the "teleport" probability, the chance of landing anywhere in the country drawn
from the prior. At `epsilon=1`, `R=30` gives several percent. Always check the reported
teleport probability when changing `R` or `epsilon` defaults.

**The population prior is mixed resolution.** England and Wales use census Output Area
populations split evenly within each area; Scotland publishes per-postcode figures, which
are finer; Northern Ireland has no source and falls back to uniform. The guarantee is
unaffected — any prior is admissible — but cross-national utility comparisons are not
like-for-like.

**Exceptions take the PEP 8 `Error` suffix** (`InvalidPostcodeError`, not
`InvalidPostcode`). Ruff's N818 enforces this; the spec was changed to match rather than
carrying a lint exemption.

**Use `scipy.spatial.KDTree`, not `cKDTree`.** The type checker cannot resolve the legacy
alias. They are the same implementation.

**The ty pre-commit hook id is `ty`, not `ty-check`.**

## Testing expectations

Test-driven development throughout: write the failing test, watch it fail for the right
reason, then implement.

**Mutation-check any test that asserts an invariant.** This is established practice here,
not a nicety. Several tests in this repository passed on first write and would have been
worthless; deliberately breaking the implementation and confirming the test catches it is
how they earned trust. It is also how the pruning flaw and the support-truncation bug were
both demonstrated rather than argued.

**Prefer exhaustive enumeration over sampling.** The mechanism is a closed-form discrete
distribution and the sampler is a pure function of one uniform. On small graphs, enumerate
every `(x, x', y)` triple — that is a proof for that graph, not evidence about it.
Statistical tests are a last resort and must be seeded; a flaky test in a privacy library
teaches people to re-run failures.

**The CI operating-system matrix is load-bearing.** Golden determinism tests only prove
cross-platform stability if they run on more than one platform. Do not trim it for speed.

## Attribution

**The core idea is not this project's.** Metric differential privacy over shortest-path
graph distance is **Geo-Graph-Indistinguishability**, by Takagi, Cao, Asano and Yoshikawa
(arXiv:2010.13449), who also give the Graph-Exponential Mechanism. Do not describe the
graph-hop approach as novel here. What this library adds is narrow and is listed in
`docs/references.md`. Keep claims there accurate; one item is explicitly marked as needing
confirmation from the full papers before it is claimed.

## Repository conventions

- `todo.md` is gitignored working scratch. The design of record is in
  `docs/superpowers/specs/`.
- `docs/` is the published MkDocs site; `docs/superpowers/` is excluded from it.
- **No placeholder figures on the documentation site.** Where a chart is missing, the page
  says so and says why. Invented numbers in a privacy library's documentation get
  screenshotted and quoted back.
- `mkdocs build --strict` runs in CI, so broken internal links fail the build.
- `site_url` and `repo_url` in `mkdocs.yml` are unconfirmed guesses and need checking
  against the real repository before the site is published.
