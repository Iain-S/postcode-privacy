# postcode-privacy — design of record

Status: accepted, 2026-09-25. Implementation sequencing lives in `todo.md`.

## Context

There is no open library that applies differential privacy to UK postcodes, and the
ad-hoc alternatives are bad. Analysts who need to share person-level data either drop
the postcode entirely (destroying geographic analysis), truncate it to the outward code
(no formal guarantee, wildly uneven protection), or round coordinates (trivially
invertible). Meanwhile off-the-shelf geo-privacy tools assume locations are points on a
plane, which fits UK postcodes badly: a postcode unit is a delivery round, not a point,
and its real-world size varies by four orders of magnitude between a city-centre tower
block and a Highland glen. Metric privacy measured in metres therefore gives a Glasgow
resident strong protection and a Sutherland resident almost none, while claiming the
same ε for both.

This library takes the other route. It builds a **graph of UK postcodes**, where nodes
are postcode units and edges join geographic neighbours, and measures privacy in
**hops** rather than metres. Density adaptation then comes for free: three hops is
~200 m in central Leeds and ~6 km on Bodmin Moor, which is the correct behaviour,
because the privacy question is "how many other people could I be?", not "how many
metres away am I?".

**Scope of v1 (fixed by brainstorming):** local differential privacy on *individual*
postcodes — given a person's real postcode, emit a different real postcode such that the
true one is deniable. Central/aggregate DP (noisy counts by geography) is explicitly out
of scope and is a separate project.

**Decisions taken:**

| Decision | Choice |
|---|---|
| Guarantee | Metric DP with graph-hop distance |
| Repeat releases | Keyed-deterministic per subject (same person → same output, always) |
| Deliverable | pip-installable Python library + CLI |
| Disconnected components | Bridge edges — sea crossings cost one hop |
| Mechanism prior | Population-weighted by default, `prior="uniform"` switchable |
| v1 rigour | Adversary/attack suite **and** a written methods note with proofs |

---

## The mechanism

### Guarantee

Let `d(x, y)` be shortest-path hop distance on the postcode graph, and let
`d̃(x, y) = min(d(x, y), R)` for a configured cap `R`. The mechanism is

```
K(x)(y)  =  π(y) · exp(−ε · d̃(x, y) / 2)  /  Z(x)
```

where `π(y)` is the prior mass of postcode `y` (population by default) and `Z(x)` is the
normaliser. This satisfies **ε·d̃-privacy**:

> For any two postcodes `x, x'` and any output `y`,
> `K(x)(y) / K(x')(y) ≤ exp(ε · d̃(x, x'))`.

**Proof sketch** (goes in the methods note, in full). `d̃` is a metric because the
truncation `min(d, R)` of a metric is a metric. By the triangle inequality
`|d̃(x,y) − d̃(x',y)| ≤ d̃(x,x')`, so the numerator ratio is at most
`exp(ε·d̃(x,x')/2)`. Separately `Z(x') ≤ exp(ε·d̃(x,x')/2)·Z(x)` by the same bound
applied termwise. Multiplying gives the result. ∎

Plain-English version for the README: *two postcodes `h` hops apart produce outputs
whose likelihoods differ by at most `e^(ε·h)`; beyond `R` hops the mechanism draws no
further distinction.*

### Why the cap R is a feature, not a fudge

Every practical implementation of an exponential mechanism over 1.7M nodes must truncate
somewhere. The usual approach — BFS to radius `R`, renormalise over the ball — **breaks
pure DP**, because a `y` inside `x`'s ball but outside `x'`'s ball gets probability zero
under `x'` and the likelihood ratio is unbounded. Most implementations quietly have this
bug.

Capping the *metric* instead of the *support* avoids it entirely. Every node in the
country retains non-zero probability: nodes beyond `R` hops all share the floor weight
`exp(−ε·R/2)`, so their total mass is computable in closed form as
`exp(−ε·R/2) · (Π_total − π(B_R(x)))` without enumerating them. The result is an **exact
sample from the exact mechanism**, with no approximation and no δ, at the cost of a BFS
over a bounded ball.

The price is a small "teleport" probability — mass that lands uniformly-by-population
anywhere in the UK. The library must **compute and report this probability**, and choose
`R` by default to keep it under a target (default `1e-6`). For ε=1/hop that is roughly
`R≈60`, a ball of ~10–15k nodes. `R` too small is a silent utility disaster (at `R=30`,
ε=1, teleport probability is several percent), so `Mechanism.__init__` must warn when
the configured `R` implies a teleport probability above the target.

### Sampling

Per *distinct* input postcode, not per row:

1. BFS from `x` out to `R` hops over the CSR adjacency, yielding `(node, hop)` pairs.
2. Weight `w = π · exp(−ε·h/2)` over the ball; add the closed-form outside mass.
3. Build the CDF once; cache it (LRU) keyed by `(postcode, ε, R, prior)`.
4. Draw `u`, inverse-CDF. If `u` lands in the outside mass, draw from a precomputed
   alias table over `π` and reject-resample while the draw is inside `B_R(x)`
   (rejection probability is tiny by construction).

Datasets have far fewer distinct postcodes than rows, so step 1–3 amortises away.

### Keyed determinism

`u` is not random. It is

```
u = HMAC-SHA256(key, subject_id ‖ postcode) → uniform [0, 1)
```

so the same subject always maps to the same output with no stored state, repeated
releases leak nothing further, and ε is spent once regardless of how many times the
pipeline runs.

Two consequences that must be documented loudly, not buried:

- **The key is as sensitive as the raw data.** Anyone holding the key and the graph can
  invert the perturbation exactly. Key handling guidance belongs in the README, and the
  CLI must refuse a key passed as a command-line argument (shell history), accepting only
  a file path or environment variable.
- **Movers are an open problem.** Keying on `(subject, postcode)` means a subject who
  moves gets an independently drawn new output, which costs a second ε and whose
  relationship to the first output leaks information about the move. Keying on `subject`
  alone instead correlates the two outputs through a shared quantile. v1 takes the
  former and states the limitation explicitly in the methods note; it is not silently
  resolved.

---

## Architecture

```
postcode_privacy/
  graph/
    build.py        ONSPD CSV → Delaunay → prune → bridge → artefact
    prune.py        adaptive long-edge removal
    bridge.py       component detection + nearest-component bridging
    prior.py        population prior from census OA populations
    artefact.py     save/load, schema version, provenance hash
  mechanism/
    hop.py          HopMechanism: weights, CDF, cap-R closed form
    sample.py       BFS ball, alias table, inverse-CDF draw
    prf.py          HMAC → uniform; key loading and refusal rules
    calibrate.py    solve for ε given a utility or attack target
  evaluate/
    utility.py      displacement km, % same LSOA/MSOA/LAD, by urban/rural
    attack.py       Bayesian re-identification; averaging attack on repeats
  cli.py            build / perturb / report / calibrate
docs/
  methods.md        formal statement, proofs, sampler correctness, limitations
```

Each module is independently testable and none needs the others' internals: the graph
build emits an artefact file, the mechanism consumes an artefact and emits
distributions, evaluation consumes a mechanism and emits numbers.

### Graph construction

`scipy.spatial.Delaunay` over **OSGB36 eastings/northings** from ONSPD (projected, so
Euclidean distance is honest) gives a planar adjacency with mean degree ~6 regardless of
local density — precisely the density-adaptive property we want, and far better behaved
than k-nearest-neighbours, which produces asymmetric edges and hops across estuaries.

Pruning must be **adaptive, not a fixed length threshold** — a 5 km cutoff is absurd in
central Manchester and over-aggressive in Caithness. Drop edge `(u,v)` when its length
exceeds `α ·` the larger of the two endpoints' median incident edge lengths, `α` default
3. This removes the spurious long convex-hull edges around the coastline and most
water-crossings, while leaving rural graphs connected.

Then bridge: find connected components, connect each to its nearest neighbouring
component by the shortest inter-component centroid pair, marked as a bridge edge. This
keeps Scilly, Orkney, Shetland, Arran, the Isle of Wight and Northern Ireland inside the
guarantee. (`bridge_cost` is a config knob if a future version wants sea crossings to
cost more than one hop; v1 ships cost 1.)

Restrict nodes to **live postcodes only** (`doterm` empty in ONSPD) — emitting a
terminated postcode would be an obvious tell.

### The prior

ONSPD carries no population figure, but it maps every postcode to a 2021 Census Output
Area, and OA populations are published under OGL. `π(postcode)` = OA population split
evenly across the live postcodes in that OA. This is a second small download and is
**optional**: absent it, fall back to `prior="uniform"` with a warning rather than
failing.

### Data and licensing

**The library ships no postcode data.** GB postcodes in ONSPD are OGL, but Northern
Ireland (`BT`) postcodes carry a restrictive Land & Property Services end-user licence
and may not be redistributed. `postcode-privacy build` therefore consumes the user's own
ONSPD download and writes an artefact to a local cache. This sidesteps licensing
entirely and is necessary anyway — the artefact is far too large for a PyPI wheel. Ship
a small synthetic fixture graph for tests, plus a `--gb-only` build flag for users who
need a redistributable artefact.

### Integer weights, not floats

The mechanism's weights are quantised to `uint64` and the CDF search runs in integer
arithmetic. Two reasons, both load-bearing:

1. **Float leakage.** Mironov (2012), *On Significance of the Least Significant Bits in
   Differential Privacy*, showed that naive floating-point implementations of continuous
   DP mechanisms leak the true input through the low bits of the IEEE representation —
   a real and exploited class of bug in DP libraries. Our mechanism is already discrete
   over a finite set, so integer weights make it structurally immune rather than
   defended by patching.
2. **Determinism.** We promise the same subject always maps to the same output. With
   float weights that promise depends on summation order, NumPy version and platform,
   and would break silently. Integer weights make it bit-exact.

Quantisation error is bounded and folded into the reported effective ε, exactly as the
radius cap is. Node ordering within the CDF is canonical (sorted by postcode) so the
mapping is stable across artefact rebuilds of the same ONSPD release.

---

## Interface

### Python API

```python
from postcode_privacy import PostcodeGraph, HopMechanism, Key, calibrate

g = PostcodeGraph.load("~/.cache/postcode-privacy/onspd-2026-05.ppg")
key = Key.from_env("POSTCODE_PRIVACY_KEY")

m = HopMechanism(g, epsilon=0.8, prior="population")  # radius chosen automatically

m.perturb("LS2 9JT", subject_id="patient-0041", key=key)  # -> 'LS6 1AA'
m.perturb_many(postcodes, subject_ids, key=key)  # -> list[str]
m.perturb_frame(df, postcode_col="pcd", subject_col="id", key=key)

m.distribution("LS2 9JT")  # exact, inspectable — the auditable object
m.report("LS2 9JT")  # hop + displacement quantiles, teleport probability

calibrate(g, target="median_displacement_km", value=2.0)  # -> ε
```

**`PostcodeGraph`** — `build(onspd_path, *, oa_population_path=None, gb_only=False,
prune_alpha=3.0, bridge_cost=1)`, `load`, `save`; `n_nodes`, `provenance` (ONSPD
release, source SHA-256, build parameters, schema version, library version),
`neighbours(pc)`, `hops(a, b)`, `__contains__`.

**`HopMechanism`** — constructed with `epsilon`, optional `radius` (else solved for from
`max_teleport`, default `1e-6`), `prior` (`"population"` / `"uniform"` / explicit array).
Exposes `radius` and `teleport_probability` as read-only attributes, and **warns at
construction** if a user-supplied `radius` implies a teleport probability above target.

**`Distribution`** — the exact mechanism output for one input: `.postcodes`, `.weights`
(integers), `.probabilities`, `.hops`, `.teleport_mass`. Making this a first-class
inspectable object is what lets auditors and tests interrogate the mechanism directly
rather than inferring it from samples.

**`Key`** — wraps key material and refuses to render it: `__repr__` and `__str__` return
`<Key …>`, never the bytes, so it cannot be logged or tracebacked into a file.
`Key.generate()`, `Key.from_file(path)`, `Key.from_env(var)`. No constructor from a
plain string.

**Errors** — distinct types so callers can branch: `UnknownPostcode`,
`TerminatedPostcode`, `MissingSubjectId`, `ArtefactVersionMismatch`. Input postcodes are
normalised (case, internal whitespace) before lookup.

### CLI

```
postcode-privacy build   --onspd ONSPD.csv [--oa-populations pop.csv]
                         [--gb-only] [--fetch] -o artefact.ppg
postcode-privacy perturb IN.csv -o OUT.csv --graph artefact.ppg --epsilon 0.8
                         --postcode-col pcd --subject-col id --key-file k
                         [--on-unknown error|drop|null]
postcode-privacy report  --graph g.ppg --epsilon 0.8 [--postcode "LS2 9JT" | --sample N]
postcode-privacy calibrate --graph g.ppg --target median-displacement-km=2.0
postcode-privacy keygen  -o key.bin
```

`--fetch` resolves and downloads the current ONSPD release from the ONS geoportal, so
the common path is one command. Best-effort — the quarterly URL changes — with a clear
manual fallback in the error message.

**The CLI never accepts a key as an argument value**, only `--key-file` or
`POSTCODE_PRIVACY_KEY`, because command lines land in shell history and process listings.
`perturb` prints the effective ε, radius and teleport probability to stderr on every run,
so the privacy parameters appear in pipeline logs rather than being invisible.

---

## Testing strategy

Tooling: **pytest**, **ruff** (lint + format), **ty** (type checking), **hypothesis**
(property-based), **uv** for environments, all wired through pre-commit and CI.

The governing principle: **the mechanism is a closed-form discrete distribution and the
sampler is a pure function of a single uniform `u`.** Separating those two means almost
everything can be tested exactly, and the suite should end up with barely any statistical
assertions in it. A flaky test in a privacy library is corrosive — people learn to re-run
it, and then a real failure gets re-run too.

### Tier 1 — exhaustive and exact (where the privacy lives)

No randomness involved. On small synthetic graphs (≤50 nodes) we enumerate rather than
sample:

- **The DP inequality, brute-forced.** For every `(x, x', y)` triple, assert
  `K(x)(y)/K(x')(y) ≤ exp(ε·d̃(x,x'))`. This is not an estimate of the guarantee — it is
  a proof of it for that graph.
- **Normalisation.** Integer weights sum exactly to the stated total; probabilities sum
  to 1.
- **Cap correctness.** The closed-form out-of-ball mass equals the explicitly enumerated
  sum on a graph small enough to enumerate fully.
- **Metric axioms.** `d̃ = min(d, R)` is symmetric and satisfies the triangle inequality
  over all triples.

### Tier 2 — the sampler as a pure function

`inverse_cdf(cdf, u)` is deterministic. Test it at `u = 0`, at each exact CDF breakpoint,
immediately either side of each breakpoint, and at the maximum representable `u`. This is
exhaustive, not sampled. The only remaining randomness is whether `u` is uniform, which
is HMAC-SHA256's problem — what *we* test is our 256-bits-to-uniform conversion for
modulo bias, again a deterministic property.

### Tier 3 — differential testing against a naive reference

A deliberately slow, obviously-correct `_reference.py`: dense Floyd–Warshall, full
enumeration, no radius cap, no alias table, no caching, floats throughout. Assert the
optimised implementation matches it on Hypothesis-generated small graphs. This is how the
BFS/cap/integer/cache machinery earns trust — the clever version is checked against a
version too simple to be wrong.

### Tier 4 — analytic oracles

On a path graph, a cycle graph and a complete graph, `K` has a closed form (geometric and
uniform respectively). Compare exactly.

### Tier 5 — properties and metamorphic relations (Hypothesis)

Relations that must hold without knowing the answer, over generated graphs, ε and priors:

- Probability is non-increasing in hop distance under a uniform prior.
- ε → 0 converges to the prior; ε → ∞ converges to a point mass at `x`.
- Relabelling node ids permutes the distribution identically.
- Increasing ε never increases expected hop displacement.
- Round-tripping an artefact through save/load is bit-identical.

### Tier 6 — golden/determinism tests

A checked-in fixture graph, a fixed key and fixed subject ids, with expected output
postcodes committed to the repo as literals. This is what catches an accidental change to
the PRF, to node ordering, or to weight quantisation — any of which would silently break
the promise that a subject's output never changes. Because weights are integers and node
order is canonical, these goldens must be stable across platforms, and CI should run them
on Linux and macOS to prove it.

### Tier 7 — where statistics are genuinely unavoidable

Only two places, and both are contained:

- **One seeded end-to-end G-test** that the full pipeline reproduces the analytic
  distribution. Seeded, therefore deterministic, therefore never flaky.
- **Attack and utility numbers are reported by a benchmark, not asserted by a test.**
  `pytest --benchmark` / a separate non-blocking CI job emits the table; only very loose
  regression guards apply (e.g. "averaging attack recovers <5% in keyed mode"). These
  numbers are evidence for the methods note, not pass/fail gates.

### Tier 8 — build-level checks

- The built wheel contains no postcode data (inspect artefact contents in CI).
- `Key.__repr__` never emits key material — asserted directly, including inside a
  formatted traceback.

---

## Known open questions

- **Movers.** Keying on `(subject, postcode)` leaks that a move occurred. Documented as a
  v1 limitation; a proper treatment needs a sequential-release analysis.
- **Bridge plausibility.** A Scilly resident can be reported in Cornwall. Correct for
  privacy, potentially startling for users; the `bridge_cost` knob exists but v1 does not
  tune it.
- **Delaunay across the border.** Anglo-Scottish and any Irish land-border edges are kept
  deliberately — administrative boundaries should not create privacy cliffs — but this
  will surprise some users and needs calling out in the docs.
