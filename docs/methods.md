# Methods

The formal content of this library: what is guaranteed, why, and what is not.

!!! abstract "The idea is not ours"
    Metric differential privacy over shortest-path distance on a graph is
    **Geo-Graph-Indistinguishability**, due to Takagi, Cao, Asano and Yoshikawa
    ([arXiv:2010.13449](https://arxiv.org/abs/2010.13449)), who also give the
    Graph-Exponential Mechanism. It rests on metric differential privacy
    (Chatzikokolakis et al., PETS 2013) and the exponential mechanism (McSherry and
    Talwar, FOCS 2007). What this library adds is set out in
    [References](references.md) and is narrower than the method itself.

## 1. Setting

Let \(G = (V, E)\) be a finite, undirected, connected graph whose vertices are UK
postcode units. Let \(d(x,y)\) be the shortest-path **hop** distance in \(G\), and fix
a radius \(R \in \mathbb{N}\). Write

\[
\tilde{d}(x,y) \;=\; \min\bigl(d(x,y),\, R\bigr).
\]

Let \(\pi : V \to \mathbb{Z}_{>0}\) be a **prior**, strictly positive, by default the
residential population of each postcode. Write \(\Pi = \sum_{y \in V} \pi(y)\), and
\(q = e^{-\varepsilon/2}\).

The mechanism \(K\) maps a true postcode to a released one:

\[
K(x)(y) \;=\; \frac{\pi(y)\, q^{\tilde{d}(x,y)}}{Z(x)},
\qquad
Z(x) \;=\; \sum_{y \in V} \pi(y)\, q^{\tilde{d}(x,y)}.
\]

Every postcode in the country has non-zero probability. That is not incidental; it is
what makes the next section true.

## 2. The guarantee

!!! success "Theorem"
    \(K\) satisfies \(\varepsilon\tilde{d}\)-privacy. For all \(x, x', y \in V\),
    \[
    \frac{K(x)(y)}{K(x')(y)} \;\le\; e^{\varepsilon\, \tilde{d}(x,x')}.
    \]

**Step 1 — \(\tilde{d}\) is a metric.** Non-negativity, identity and symmetry are
inherited from \(d\). For the triangle inequality, take any \(x, y, z\). If either
\(\tilde{d}(x,y)\) or \(\tilde{d}(y,z)\) equals \(R\), then their sum is at least \(R\),
which is at least \(\tilde{d}(x,z)\) by definition of the cap. Otherwise both equal the
true distance, and
\(\tilde{d}(x,y) + \tilde{d}(y,z) = d(x,y) + d(y,z) \ge d(x,z) \ge \tilde{d}(x,z)\).

**Step 2 — reverse triangle inequality.** For any \(x, x', y\),
\(\bigl|\tilde{d}(x,y) - \tilde{d}(x',y)\bigr| \le \tilde{d}(x,x')\), which follows from
step 1 applied in both directions.

**Step 3 — the numerators.** Since \(0 < q < 1\),

\[
\frac{\pi(y) q^{\tilde{d}(x,y)}}{\pi(y) q^{\tilde{d}(x',y)}}
= q^{\tilde{d}(x,y) - \tilde{d}(x',y)}
\le q^{-\tilde{d}(x,x')}
= e^{\varepsilon \tilde{d}(x,x') / 2}.
\]

The prior cancels exactly. This is why **any** strictly positive prior is admissible.

**Step 4 — the normalisers.** Applying step 2 termwise,

\[
Z(x') = \sum_y \pi(y) q^{\tilde{d}(x',y)}
\;\le\; \sum_y \pi(y) q^{\tilde{d}(x,y) - \tilde{d}(x,x')}
= e^{\varepsilon \tilde{d}(x,x') / 2} \, Z(x).
\]

**Step 5.** Multiplying steps 3 and 4 gives
\(K(x)(y)/K(x')(y) \le e^{\varepsilon \tilde{d}(x,x')}\). \(\blacksquare\)

In words: **two postcodes \(h\) hops apart produce outputs whose likelihoods differ by
at most \(e^{\varepsilon h}\); beyond \(R\) hops the mechanism draws no further
distinction.** The factor of two in \(q = e^{-\varepsilon/2}\) is exactly what pays for
the normaliser in step 4.

### Verified, not merely argued

The suite does not take this proof on trust. On generated graphs it enumerates **every**
triple \((x, x', y)\) and checks the inequality directly — a proof for each graph rather
than evidence about it — and the test is mutation-checked: it catches a missing factor
of two in the exponent, and it catches the error in the next section.

## 3. Why the cap is on the metric and not the support

No implementation can evaluate \(Z(x)\) over 1.7 million nodes per query without
stopping somewhere. The obvious approach is to walk out \(R\) hops and renormalise over
that ball:

\[
K'(x)(y) \;\propto\; \pi(y)\, q^{d(x,y)} \cdot \mathbb{1}\bigl[d(x,y) \le R\bigr].
\]

**This is not differentially private at any \(\varepsilon\).** Take neighbours \(x, x'\)
with \(d(x,x') = 1\) and a vertex \(y\) with \(d(x,y) = R\) and \(d(x',y) = R+1\). Then
\(K'(x)(y) > 0\) while \(K'(x')(y) = 0\), so the likelihood ratio is unbounded and no
\(\varepsilon\) satisfies the definition. The failure is silent: the mechanism looks
correct, samples plausibly, and reports a finite \(\varepsilon\) that it does not have.

Capping the metric avoids this entirely while costing the same work. Every vertex beyond
the cap shares the floor weight \(q^{R}\), so the mass outside the ball is available in
closed form:

\[
Z(x) \;=\; \sum_{h=0}^{R-1} q^{h}\, \pi(S_h)
\;+\; q^{R}\Bigl(\Pi - \sum_{h=0}^{R-1} \pi(S_h)\Bigr),
\]

where \(S_h\) is the set of vertices exactly \(h\) hops from \(x\). Only the shells
inside the ball are enumerated; the rest of the country contributes through
\(\Pi\), a single precomputed constant.

The price is a **teleport probability** — the chance of landing beyond the cap, drawn
from the prior, anywhere in the country:

\[
\Pr[\text{teleport}] \;=\; \frac{q^{R}\bigl(\Pi - \pi(B_R(x))\bigr)}{Z(x)}.
\]

The library computes this exactly, reports it, and chooses \(R\) by default to hold it
below \(10^{-6}\). A radius chosen too small does not fail loudly — it quietly inflates
this — so supplying one explicitly produces a warning when it misses the target.

## 4. Sampling

Sampling is in two stages, which is a correctness-preserving decomposition rather than
an approximation.

1. **Choose a shell.** Select \(h \in \{0, \dots, R-1\}\) with probability proportional
   to \(q^{h} \pi(S_h)\), or the tail with probability proportional to
   \(q^{R}(\Pi - \pi(B_R(x)))\).
2. **Choose within it.** Select \(y \in S_h\) with probability proportional to
   \(\pi(y)\) alone. For the tail, draw \(y\) from \(\pi\) over all of \(V\) and reject
   while the draw lies inside the ball.

For \(y \in S_h\) this gives

\[
\Pr[y] = \frac{q^{h}\pi(S_h)}{Z(x)} \cdot \frac{\pi(y)}{\pi(S_h)}
       = \frac{\pi(y)\, q^{h}}{Z(x)},
\]

which is \(K(x)(y)\) exactly.

**Why decompose at all.** A single flat cumulative distribution over \(V\) would have to
span the total prior mass — around \(2^{26}\) people — multiplied by the exponential's
dynamic range \(e^{\varepsilon R/2}\), multiplied by whatever precision the smallest
weights require. At every usable pair of parameters that exceeds \(2^{64}\), so a
64-bit integer cumulative array cannot hold it and a floating-point one reintroduces
precisely the leakage integers were chosen to avoid. Split in two, neither stage is
large.

### Integer arithmetic

Weights are exact integers. The prior is integral by construction, and the powers
\(q^{h}\) are represented as integers scaled by a power of two, so the only rounding
anywhere in the mechanism is in those powers. Two reasons:

- **Floating-point implementations of DP mechanisms leak.** Mironov (CCS 2012) showed
  that the low bits of an IEEE representation can reveal the true input. A discrete
  mechanism over a finite set has no need to take that risk.
- **Determinism.** The promise that a subject's output never changes would otherwise
  depend on summation order, library version and platform. Integer weights make it
  bit-exact, and continuous integration runs golden tests on Linux and macOS to prove it.

#### Rounding, and why it does not weaken the bound

Integer powers raise an obvious question: the theorem above is stated for the real
number \(q^{h}\), and the implementation ships something else. The gap is not
automatically harmless. Evaluating each power independently in double precision and
rounding it — \(P_h = \mathrm{round}(2^{s}\,\texttt{exp}(-\varepsilon h/2))\) — errs in
both directions, and when one hop's error lands low after its predecessor's landed high,
the implemented likelihood ratio exceeds \(e^{\varepsilon h}\). On a two-node graph with
\(\varepsilon = 0.3\), \(R = 1\) and a prior spanning the 64-bit range, the excess is
\(1.25 \times 10^{-17}\). Numerically that is nothing. Formally it makes the theorem
false, and a privacy library's theorem has to be true as stated.

The error that mattered came from the double rather than from the integer: at
\(\varepsilon = 0.3\) the floating-point exponential was off by \(4.7 \times 10^{-18}\)
relative, some 170 times one unit in the last place of the scaled integer.

Inspecting the proof shows exactly what the integer sequence has to satisfy. Steps 1
and 2 use \(q^{h}\) only through the inequality \(q^{a} \le q^{-h} q^{b}\) whenever
\(|a - b| \le h\); since \(P\) is non-increasing the binding case is \(a = b - h\). So
the guarantee holds for *every* triple if and only if

\[
P_{j+h} \;\ge\; q^{h} P_j \qquad \text{for all } j,\, h \text{ with } j + h \le R.
\]

The implementation builds a sequence with that property by construction rather than
hoping for it, and does so without a float anywhere. It takes a dyadic rational
\(\hat q \ge q\) — a 60-digit correctly-rounded decimal exponential, nudged upward, over
an exponent computed at a precision no double can overflow — and sets

\[
P_0 = 2^{s}, \qquad P_{j+1} = \lceil \hat q\, P_j \rceil .
\]

Each step satisfies \(P_{j+1} \ge \hat q P_j \ge q P_j\) exactly, and the general case
follows by induction. The error is therefore one-sided: the implemented weights decay
slightly *more slowly* than the ideal ones, which is the direction that gives away a
sliver of utility rather than a sliver of privacy. The mechanism satisfies the
\(\varepsilon\) that was requested, exactly, with no effective-epsilon correction to
report.

The sliver is small. The scale \(s\) is chosen so that \(P_R\) retains 64 bits of
precision after both the exponential decay and the accumulated rounding-up, which puts
the relative deviation of every \(P_h\) from \(2^{s} q^{h}\) below \(1.5 \times
10^{-20}\) across \(\varepsilon \in [0.01, 5]\) at \(R = 60\) — some four orders of
magnitude finer than double precision.

This is checked in exact rational arithmetic, two ways.
`tests/test_dp_guarantee_exact.py` enumerates every \((x, x', y)\) triple on small
graphs and compares the exact ratio of integer weights against a rational *lower* bound
on \(e^{\varepsilon h}\), so no violation can hide behind a floating-point tolerance;
the counterexample above is a regression test. It also checks the sharp inequality
\(P_{j+h} \ge q^{h} P_j\) directly, because on any particular graph the end-to-end ratio
sits below its bound with room to spare, and a sub-unit error in one power need not
surface there. The second test is what makes the claim hold for every graph and prior
rather than the ones a generator happened to produce.

#### Supported bounds on the prior

Two conditions, both enforced at construction:

- Every node needs \(\pi(y) \ge 1\). A node with zero prior can never be produced, so it
  could hide nobody, and the likelihood ratio against it would be unbounded.
- The *total* prior mass must not exceed \(2^{62}\). Weights are unbounded Python
  integers and need no ceiling, but the sampler accumulates the prior itself in `int64`,
  and a cumulative sum that wraps would draw from a silently wrong distribution. The
  check is made in floating point before the integer sum is taken, because an `int64`
  sum of an oversized prior wraps before it can be inspected. For reference, the United
  Kingdom's population is about \(2^{26}\).

### Keyed determinism

The uniform driving the sampler is not random. It is

\[
u \;=\; \mathrm{HMAC\text{-}SHA256}\bigl(\text{key},\; \text{subject\_id} \,\|\, 0\mathrm{x}00 \,\|\, \text{postcode}\bigr),
\]

reduced to the required range by rejection rather than modulo, so it is unbiased. The
same subject therefore always receives the same output, with no stored state.

This is how repeated publication is handled. It is **not** a composition theorem: there
is no accumulation to bound, because there is only ever one output per subject —
*provided* the key, the subject identifier, the true postcode, the graph artefact, the
parameters and the library's output-stability version are all unchanged. When any of
those differs the two releases are two draws and the loss composes in the ordinary way.
The conditions are listed in full in the
[threat model](threat-model.md#when-repeated-releases-count-as-one-observation).

Deriving the draw from a key rather than from fresh randomness also changes what kind of
guarantee this is: the shipped mechanism satisfies *computational*
\(\varepsilon\tilde{d}\)-privacy, under the assumption that HMAC-SHA256 is a
pseudorandom function. The experiment is stated precisely in the
[threat model](threat-model.md#the-guarantee-is-computational-not-information-theoretic).

Measured, at \(\varepsilon = 2\) over 20 postcodes, with a Bayesian adversary holding
the population prior and a candidate set verified to contain the true postcode in every
case:

| releases seen | identifies the exact postcode | median rank of the truth | median \(P(\text{truth})\) |
|---|---|---|---|
| one | 2 / 20 | 15th | 0.017 |
| twenty, independent draws | **18 / 20** | **1st** | **0.903** |
| twenty, keyed | 4 / 20 | 12th | 0.020 |

Twenty independent releases of the same subject destroy the protection outright. Twenty
keyed releases leave the adversary where a single release did — the difference between
2/20 and 4/20 is well inside sampling noise at this sample size, and both reflect one
observation's worth of information. That is what keyed determinism buys, and it is the
only reason repeated publication is safe here.

Note also what the first row says about \(\varepsilon = 2\) itself: a *single* release
already lets this adversary pinpoint the exact postcode for one subject in ten. Two is
not a cautious choice of \(\varepsilon\).

## 5. What is not claimed

- **The prior is not part of the guarantee.** It cancels in step 3. Changing it changes
  *which* postcode within a shell is chosen, and therefore how many real people an
  output could plausibly have come from, but not the bound.
- **The graph is a modelling choice.** \(\varepsilon\tilde{d}\)-privacy holds for
  whatever graph is supplied. Whether a hop *means* anything is a question about the
  construction, not about the proof, and the construction has known defects — see
  [Limitations](limitations.md).
- **No composition across different secrets.** Releasing a subject's postcode and their
  employer's postcode spends privacy twice; nothing here bounds that.
- **A subject who moves is a second secret.** The key is derived from the postcode as
  well as the subject, so a move produces an independent draw at a second
  \(\varepsilon\), and the relationship between the two outputs leaks that a move
  occurred.
- **The guarantee is computational.** The randomness is over a uniformly drawn secret
  key, and HMAC-SHA256 is assumed to be a pseudorandom function. The ideal mechanism's
  bound is information-theoretic; the implementation inherits it up to the PRF
  advantage. See the [threat model](threat-model.md).
- **Key compromise removes the guarantee entirely.** An adversary holding the key and
  the graph can evaluate the mechanism themselves and eliminate every postcode that does
  not map to the observed output. The surviving candidate set is usually small but is
  not always a single postcode; the mapping has collisions. Treat compromise as
  disclosure of the source postcodes.
- **Local DP protects the field, not the record.** Nothing here hides that a record
  exists or what its other columns say. See the
  [threat model](threat-model.md#where-this-sits-against-the-icos-guidance).
- **The implementation is unreviewed.** It has tests, mutation checks and
  cross-platform golden outputs, but it has had no external audit, and a privacy
  guarantee is a property of an implementation as much as of a theorem.
