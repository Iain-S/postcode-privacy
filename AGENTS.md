# Working on postcode-privacy

Things that are not obvious from reading the code or the docs. Read this before changing
anything.

> **Keep this file current.** If you change a default, a guarantee, a guard, or any of the
> decisions recorded here, update this file in the same commit.

## Things that look wrong but are deliberate

**The 50 km edge cut is on by default and is NOT the same thing as `prune_alpha`.**
`max_edge_km` makes an absolute claim — no two UK postcodes 50 km apart are neighbours —
whereas `prune_alpha` makes a density judgement, which is why one can be a default and
the other cannot. Measured on the August 2026 build it removes 264 edges of 5.36
million, fragments nothing, and needs no bridging. It cut the rural p95 displacement
from 260 km to 61 km and the Isle of Lewis median from 308 km to 10 km, with
self-probability unchanged to three decimal places: a pure utility repair at no privacy
cost. Delaunay tiles the convex hull, so without it the graph contains edges like Great
Yarmouth to Shetland (920 km) and Barra to Scilly (780 km), each of which is one hop.

Do not confuse this with the Thames-at-Woolwich case, which is a 2 km edge that is a
15 km drive. That is still unfixed and no geometric rule catches it.

**Pruning and bridging are off by default. Do not enable them to "fix" the graph.**
`assemble()` returns the unmodified Delaunay triangulation. The pruning heuristic exists,
is tested, and is opt-in via `prune_alpha`. It is off because no geometric criterion can
separate an estuary from an empty moor — in a point set they are the same object, a gap
with nothing in it. Length thresholds cannot do it and neither can Gabriel or
relative-neighbourhood graphs. The information is not in the data. The real fix is road or
hydrography data, deferred to a future version.

**Bridging is not needed on the default path.** Delaunay triangulates the convex hull, so
every point is already connected — an island far offshore included. Bridging exists *only*
to repair what pruning severs, and is enabled with it. There is a test asserting this; do
not add bridging to the unpruned path.

**`check_integrity` asserts the consequence, not the cause.** `assemble()` refuses to
return a graph with isolated nodes or more than one component, because that is the
condition under which the mechanism hands back the secret — whatever produced it.
Duplicate centroids were one cause; the next will be something else. Do not weaken this
to a warning.

**The prior does not affect the guarantee, only the utility.** Any strictly positive
weighting satisfies epsilon-d-privacy; the prior cancels in the likelihood ratio. What it
decides is which postcode within a ring is chosen, and therefore how many real people an
output could have come from. Do not reason about it as if it were part of the privacy
claim.

**Population sources differ by nation and must not be levelled down.** Scotland publishes
per postcode (finest), England and Wales per 2021 output area, Northern Ireland per 2021
data zone. Splitting an area's population evenly captures variation between areas but not
within them, which recovers 1.37x of the benefit against Scotland's 2.0x and can never
identify an uninhabited postcode. Scotland's file also contains 252 *split* postcodes
carrying a trailing letter (`AB12 3GQA`/`AB12 3GQB`) where a postcode straddles a
boundary; these are summed back onto the base postcode rather than dropped, which is why
`_read_pairs` accumulates instead of assigning.

**Large-user postcodes are not nodes.** Royal Mail classes a postcode as "large user"
when it belongs to a single organisation receiving high mail volumes. Those have no
resident population to hide anyone among, so they are excluded from the graph entirely
(4.0% of live postcodes, 72,056 of them) and can never be emitted. They are *remembered*
in `PostcodeGraph.excluded` so that submitting one raises `LargeUserPostcodeError` with an
explanation, rather than `UnknownPostcodeError`, which would be true but useless for a
postcode that plainly exists. The excluded list travels in the artefact; without it a
reloaded graph gives the wrong error.

Excluding them also dissolved the worst co-located groups: the five largest clusters of
postcodes sharing one coordinate were ~100% large-user (1,161 of 1,161 at one central
London point).

**A terminated postcode as input raises `UnknownPostcodeError`, and that is a
decision.** It is a worse message than `TerminatedPostcodeError` would be, and it was
chosen anyway: distinguishing the two means carrying all 918,726 terminated postcodes in
every artefact, and the message is the only thing that improves. Behaviour is unchanged,
because the batch `on_error` policy handles those rows either way. Do not "fix" this
without weighing the artefact size again.

**Batch `on_error` defaults to `error`, and `drop` is refused by `perturb_many`.** A
dataset quietly losing rows is a worse outcome than a run that stops and says why, so the
default raises. `drop` is meaningful only where a row can genuinely be removed: taking
entries out of a list result would silently break the correspondence between input row
and output row, so the list API raises and points at `perturb_frame`.

**Known caveat, not yet resolved:** some large-user postcodes are university halls,
hospitals and prisons, where people genuinely do live and may be registered. Those
records now error rather than being perturbed.

**Duplicate coordinates are expanded, and this is load-bearing.** Qhull discards duplicate
points, so a naive triangulation leaves every postcode sharing a centroid in no simplex at
all — degree zero, infinitely far from everything. Under the capped metric such a node's
mechanism returns its own true postcode with probability very close to one: a total,
silent loss of privacy. Real ONSPD data has 57,030 of them, 3% of the country, the largest
group being 1,161 postcodes at a single point. `delaunay_edges` therefore triangulates
distinct *coordinates* and lifts the result back to nodes, so co-located postcodes are
mutually adjacent and share their outside neighbours. Do not simplify this away, and keep
the invariant tests: zero isolated nodes, one component.

**The radius cap applies to the metric, not the support.** The mechanism uses
`min(d, R)`, so every postcode in the country keeps nonzero probability and the
out-of-ball mass is computed in closed form. The obvious optimisation — BFS to radius `R`
and renormalise over that ball — **breaks pure differential privacy**, because a node
inside `x`'s ball but outside `x'`'s gets probability zero under one and not the other,
making the likelihood ratio unbounded. This is mutation-tested. Do not "simplify" it.

**The distribution is decomposed by hop shell, and that is not a stylistic choice.** A
single flat cumulative distribution over the country spans the total prior mass (~2**26
people) times the exponential's dynamic range (`exp(epsilon * R / 2)`) times the precision
the smallest weights need. At every usable pair of parameters that exceeds 2**64, so a
uint64 CDF cannot represent it and a float one reintroduces the leakage integers were
chosen to avoid. Split in two — pick a shell, then pick a node within it proportional to
the prior alone — neither stage is large, and the only rounding anywhere is in the powers
of `q`. Do not flatten this back into one cumulative array.

**The powers of `q` come from a rational recursion, never from `math.exp`.** What
shipped originally was `round(2**scale * math.exp(-epsilon/2 * h))`, evaluated
independently per hop, and it made the stated theorem false. The proof needs
`P[j+h] >= q**h * P[j]` for every `j` and `h`; that version errs in both directions, so
a hop whose error lands low after one that landed high pushes the implemented likelihood
ratio past `exp(epsilon * h)`. On a two-node graph with an int64-spanning prior the
excess over `exp(0.3)` was 1.25e-17 -- numerically nothing, formally a false theorem.

The dominant term was the double, not the integer rounding: at `epsilon=0.3` the float
`math.exp` was off by 4.7e-18 relative, 170 times one unit in the last place of the
scaled integer. So the fix has two halves and both are load-bearing. `q_upper_bound`
produces an exact dyadic rational provably at least `exp(-epsilon/2)`, via `Decimal.exp`
at 60 digits nudged upwards -- the `Decimal("0.5")` multiply runs at 1200 digits so the
exponent itself is exact rather than rounded in an unknown direction. Then `_powers`
iterates `P[j+1] = ceil(q_hat * P[j])`, which satisfies the inequality at every step and
therefore, by induction, at every pair, and errs one-sidedly towards less utility rather
than less privacy.

Do not "simplify" this back to a closed-form power and do not reintroduce `math.exp`
into the weights. `tests/test_dp_guarantee_exact.py` checks both the structural
inequality and the end-to-end triples in exact rational arithmetic;
`tests/test_dp_guarantee.py` cannot, because it converts to float and allows 1e-9 slack.
Note that the end-to-end enumeration alone does *not* catch a floor-instead-of-ceil
mutation -- on any particular graph the ratio has slack -- which is why the sharp
`P[j+h] >= q**h * P[j]` test exists alongside it.

**The total prior mass is capped at 2**62, and the check is made in float.** Weights are
unbounded Python integers, but the sampler accumulates the prior in int64. An int64 sum
of an oversized prior wraps silently, so checking the sum after taking it would pass on
exactly the input the check exists to reject. The UK's population is about 2**26, so
this cap binds on nothing real.

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

**Provenance has to distinguish two graphs, not just describe one.** Two artefacts
built from one ONSPD with different population files give every subject a different
output, and until schema 3 they carried identical provenance. `Provenance` therefore
records the prior kind and total, the name/role/SHA-256 of every population input, and
the versions of numpy, scipy and pyproj -- the triangulation and the Irish Grid
reprojection both live in dependencies, so they can move an edge without anything here
changing. Adding a build input without adding it to `Provenance` reopens the hole.

**Cite `graph_sha256`, not `source_sha256`.** The artefact's own hash identifies the
graph that produced a release; the ONSPD hash plus build flags is a recipe for
attempting a rebuild, which the library does not promise is byte-identical. The README
previously claimed the latter was sufficient and it was not.

**The perturb manifest's `prior` field is read from the artefact.** It was a hardcoded
`"population"`, which reported a uniform-prior graph as population weighted -- the one
field a reader checks to judge whether an output postcode is plausible. Do not
reintroduce a constant there.

**The shipped guarantee is computational, not information-theoretic.** The proof is
about a mechanism drawing fresh randomness; the library draws nothing, deriving every
output from HMAC-SHA256 under a secret key. The randomness is over the uniform choice of
key and HMAC is assumed to be a PRF. Headline text must not claim unconditional DP.
`docs/threat-model.md` states the experiment; keep it consistent with any change to
`mechanism/prf.py`.

**"Repeated releases leak nothing further" is conditional on six things**, all listed in
the threat model: key, subject identifier, true postcode, graph artefact, epsilon and
radius, and the output-stability version. Change any one and the two releases are two
draws composing to 2*epsilon*d. Rotating the key is therefore a privacy cost here, not
hygiene -- the opposite of the usual advice, and worth saying out loud whenever key
handling comes up.

**Do not write that key compromise lets an attacker "invert exactly".** It does not: the
keyed map is not injective and the preimage of an observed output is usually a handful of
postcodes. The accurate claim is that every postcode outside that preimage is eliminated
with certainty, so compromise should be treated as disclosure. `tests/test_key_compromise.py`
pins both halves, because overstating the consequence is as much a documentation defect
as understating it.

## Known traps

**ONSPD gives Northern Ireland grid references in the IRISH GRID.** Read as British
National Grid they place Belfast in the Derbyshire Peak District. Every range check
passed, because Irish Grid values sit comfortably inside the OSGB envelope: 61% of NI
postcodes landed within a kilometre of a real GB postcode, `BT71 7AL` sat exactly on top
of `LL26 0BH` in North Wales, and the graph carried thousands of false edges between
Belfast and Liverpool. The reader now projects NI latitude and longitude into BNG with
pyproj, and **checks every GB grid reference against its own latitude and longitude**,
refusing the file if they disagree. That check is the one that would have caught this on
day one, and it is why pyproj is a required dependency rather than an optional one.

The bug survived every test and every data validation, and was found by drawing a map
and noticing Northern Ireland was missing. But it did not have to be found that way:
**the ONSPD User Guide, which ships inside the archive, documents it in the description
of the very column we were reading.** `EAST1M` is described as "blank for postcodes in
the Channel Islands and the Isle of Man. Grid references for postcodes in Northern
Ireland relate to the Irish National Grid." Nobody read it.

Two lessons, and the second is the cheaper one. Draw the figure — but first read the
documentation that came with the data. The same paragraph also explains why Channel
Islands and Isle of Man postcodes are absent from the graph: they carry no grid
reference at all, so the reader drops them as `no_grid_reference`. That is correct, and
it is worth knowing it is intended rather than accidental.

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

**A numpy `int64` multiplied by a shell power silently wraps.** The mechanism's
weights are arbitrary-precision Python integers, and `prior[nodes].sum()` is an
`np.int64`. Multiplying the two gives a wrapped `int64`, not a wide integer, and the
symptom is an `OverflowError` somewhere else entirely or — worse — a plausible wrong
number. Convert with `int(...)` before touching `powers`. This bit `area_preservation`
on first write.

**`Adjacency.ball` returns shell-ordered nodes; `Distribution.ball` is sorted.** The
two differ and both are used. `Distribution` sorts explicitly so that `contains` can
binary-search; the raw adjacency version does not, because the mechanism only ever wants
it grouped by shell. Binary-searching the raw one silently returns wrong answers rather
than failing.

**Write `np.min(x)`, not `x.min()`.** The numpy stubs resolve the no-argument overload
to `NDArray[object_]` and the type checker rejects it. This has recurred three times.

**Use `scipy.spatial.KDTree`, not `cKDTree`.** The type checker cannot resolve the legacy
alias. They are the same implementation.

**The ty pre-commit hook id is `ty`, not `ty-check`.**

**BFS frontier expansion is vectorised, and the loop it replaced was the whole cost.**
`Adjacency.ball` gathers every frontier node's neighbours with flat index arithmetic over
the CSR rows. The obvious version — one `neighbours(node)` slice per frontier node —
cost a Python call for every node visited, two and a half million of them per
twenty-five national distributions, and was 95% of the mechanism's runtime. Vectorising
it took a national distribution from 67 ms to 23 ms, and the whole-country verification
sweep from 32 to 11 core-hours. The profile is flat now; the remaining time is split
between `np.unique` and the gather, so do not expect another easy win here.

Filter against `seen` *before* deduplicating. On a national graph a frontier's
neighbours are overwhelmingly already visited, so filtering first shrinks the array that
has to be sorted by a large factor.

## Testing expectations

Test-driven development throughout: write the failing test, watch it fail for the right
reason, then implement.

**Test generators must be able to produce the pathology.** Uniform random floats never
collide, so the point-set generators could not exercise duplicate coordinates — and a
passing connectivity test coexisted with 57,030 real postcodes having zero privacy. The
generators now force collisions deliberately. When adding a generator, ask what real
input property it structurally cannot produce.

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
- Stage files explicitly with `git add <filename[s]>`. Do not use the blanket `git add -A` as you may add data or in-progress files that have not yet been listed in .gitignore.
