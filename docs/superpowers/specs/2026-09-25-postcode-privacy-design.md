# postcode-privacy — design of record

Status: accepted, 2026-09-25. Implementation sequencing lives in `todo.md`.

## Context

There is no open library that applies differential privacy to UK postcodes, and the
ad-hoc alternatives are bad. (The *method* used here is published work — see Prior art
below and `docs/references.md`; what is missing is a usable implementation for UK
geography.) Analysts who need to share person-level data either drop
the postcode entirely (destroying geographic analysis), truncate it to the outward code
(no formal guarantee, wildly uneven protection), or round coordinates (trivially
invertible). Meanwhile off-the-shelf geo-privacy tools assume locations are points on a
plane, which fits UK postcodes badly: a postcode unit is a delivery round, not a point,
and its real-world size varies by four orders of magnitude between a city-centre tower
block and a Highland glen. Metric privacy measured in metres therefore gives a Glasgow
resident strong protection and a Sutherland resident almost none, while claiming the
same ε for both.

This library takes the other route, following Takagi et al.'s
**Geo-Graph-Indistinguishability** — metric DP over shortest-path distance on a graph
rather than over the plane. It builds a **graph of UK postcodes**, where nodes are
postcode units and edges join geographic neighbours, and measures privacy in **hops**
rather than metres. Density adaptation then comes for free: three hops is
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
| Pruning and bridging | Off by default; raw triangulation is already connected |
| Mechanism prior | Population-weighted by default, `prior="uniform"` switchable |
| v1 rigour | Adversary/attack suite **and** a written methods note with proofs |

---

## Prior art

Metric differential privacy over a graph is **not novel**, and the design should cite
rather than claim it. **Geo-Graph-Indistinguishability** (Takagi, Cao, Yoshikawa et al.,
arXiv:2010.13449; DBSec 2019), by Shun Takagi, Yang Cao, Yasuhito Asano and Masatoshi
Yoshikawa, defines exactly this notion over road networks and gives the
Graph-Exponential Mechanism for it. Their motivation is the strongest available argument
for using a graph at all: Euclidean geo-indistinguishability *overstates* the privacy it
delivers, because a real adversary knows the network and discounts outputs that are not
reachable.

What this library contributes on top of that prior work:

- The UK postcode unit as the secret space, with a graph derived from ONSPD centroids.
- A population-weighted prior, so outputs land where people actually live.
- The **capped metric** `min(d, R)`, which makes the mechanism exactly computable over
  1.7M nodes while remaining pure DP -- the usual ball-truncation does not.
- Keyed-deterministic perturbation, so repeated releases of the same subject cost one ε.
- Integer weights, closing the floating-point leakage channel.

Before the methods note is written, the GG-I papers must be read properly to check how
much of the above they already cover -- in particular whether GEM handles truncation.

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

### Pruning is off by default

Delaunay triangulates the convex hull, so it fills concavities: the Thames Estuary, the
Bristol Channel, the Wash and Morecambe Bay all get spanned, producing edges of twenty
kilometres across open water that the mechanism treats as one hop -- identical to a
literal next-door neighbour. Those artefacts are real and they damage utility.

They are nonetheless **not pruned in v1**, because no geometric criterion can fix them.
Water and empty moorland are the same thing in a point set: a gap with nothing in it.
A length threshold cannot separate the Solent from Dartmoor, and the parameter-free
alternatives do no better -- Gabriel and relative-neighbourhood graphs keep an
estuary-spanning edge for precisely the same reason, since the disc or lune over the
water contains no points. The information needed is not in the data.

An adaptive length heuristic (local scale from k nearest points, threshold `alpha` times
that, after the manner of chi-shapes) is implemented and tested, but **opt-in and off by
default**. It exists so that the diagnostic can measure what the artefacts cost against
what the heuristic costs, not because the parameter is justified. `alpha` is not a term
of art; it is this project's name for a tunable with no ground truth to tune against.

Doing this properly means supplying the missing information, which is what the GG-I work
does by using a road network: you can only cross water where a bridge exists. OS Open
Roads is OGL and that is the natural v2. The cost is that hop density would then follow
junction density rather than population.

Because pruning is off, **bridging is not needed either.** The triangulation already
connects every point, islands included -- Scilly reaches Cornwall from the outset.
Bridging exists only to repair what pruning severs, and is enabled with it.

### Duplicate centroids

Qhull discards duplicate points. In the August 2026 ONSPD, 57,030 live postcodes share a
centroid with another -- 3% of the country, the largest group being 1,161 postcodes at a
single coordinate -- so a naive triangulation leaves every one of them in no simplex,
with degree zero and infinite distance to everything else. The capped metric then gives
them back their own true postcode with probability very close to one. The privacy loss is
total, it affects a twentieth of a million people's records, and nothing errors.

The triangulation is therefore computed over distinct coordinates and lifted back to
nodes: co-located postcodes are mutually adjacent and share their outside neighbours, so
they are fully interchangeable. Sharing a centroid means being the same place, and one hop
is the right distance between them. On real data this raises mean degree from 5.81 to
9.70 and the edge count from 5.2M to 8.7M, which is affordable.

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

**Errors** — distinct types so callers can branch, named with the PEP 8 `Error`
suffix: `InvalidPostcodeError`, `UnknownPostcodeError`, `TerminatedPostcodeError`,
`MissingSubjectIdError`, `ArtefactVersionMismatchError`. Input postcodes are
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
- **Estuary shortcuts.** Raw Delaunay makes Kent and Essex one hop apart across the
  Thames Estuary. Measure how many nodes are affected and how heavy the displacement tail
  is for them before deciding whether v2 needs road-network data.
- **Road network as the graph.** The principled fix, and what the GG-I literature uses.
  Deferred, not rejected.
- **Delaunay across the border.** Anglo-Scottish and any Irish land-border edges are kept
  deliberately — administrative boundaries should not create privacy cliffs — but this
  will surprise some users and needs calling out in the docs.
