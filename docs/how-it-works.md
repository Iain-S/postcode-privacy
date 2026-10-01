# How it works

## The graph

Postcode units are the nodes. Edges come from a **Delaunay triangulation** of the postcode
centroids in the ONS Postcode Directory, using OSGB36 eastings and northings — projected
coordinates, so Euclidean distance between them is honest and no spherical correction is
needed.

Delaunay is the natural "who is my neighbour" relation for irregularly spaced points. Its
mean degree is about six regardless of local density, and that density independence is
the property everything else rests on: one hop means roughly the same thing in a city as
in a glen, even though it means wildly different numbers of metres.

## The guarantee

Let \(d(x, y)\) be shortest-path hop distance, and let \(\tilde{d}(x,y) = \min(d(x,y), R)\)
for a radius cap \(R\). The mechanism is

\[
K(x)(y) \;=\; \frac{\pi(y)\, e^{-\varepsilon\, \tilde{d}(x,y)/2}}{Z(x)}
\]

where \(\pi(y)\) is the prior weight of postcode \(y\) — residential population by default —
and \(Z(x)\) normalises. This satisfies \(\varepsilon\tilde{d}\)-privacy:

\[
\frac{K(x)(y)}{K(x')(y)} \;\le\; e^{\varepsilon\, \tilde{d}(x,x')}
\quad\text{for all } x, x', y.
\]

The proof is short. \(\tilde{d}\) is a metric, because the truncation \(\min(d, R)\) of a
metric is a metric. The triangle inequality gives
\(|\tilde{d}(x,y) - \tilde{d}(x',y)| \le \tilde{d}(x,x')\), bounding the numerator ratio by
\(e^{\varepsilon \tilde{d}(x,x')/2}\); applying the same bound termwise gives
\(Z(x') \le e^{\varepsilon \tilde{d}(x,x')/2} Z(x)\). Multiplying yields the result.

In words: **two postcodes \(h\) hops apart produce outputs whose likelihoods differ by at
most \(e^{\varepsilon h}\); beyond \(R\) hops the mechanism draws no further distinction.**

## Why the cap is sound, and the obvious alternative is not

No implementation can evaluate this over 1.7 million nodes without stopping somewhere.
The obvious approach — walk out to \(R\) hops and renormalise over that ball — **breaks
pure differential privacy**. A postcode inside \(x\)'s ball but outside \(x'\)'s gets
probability zero under \(x'\) and nonzero under \(x\), so the likelihood ratio is unbounded.

Capping the *metric* rather than the *support* avoids this entirely. Every postcode in the
country keeps nonzero probability: those beyond \(R\) hops all share the floor weight
\(e^{-\varepsilon R/2}\), so their total mass is available in closed form as
\(e^{-\varepsilon R / 2}\,(\Pi_{\text{total}} - \pi(B_R(x)))\) without enumerating any of
them. The result is an exact sample from the exact mechanism — no approximation, no
\(\delta\) — at the cost of a breadth-first search over a bounded ball.

The price is a small **teleport probability**: mass that lands anywhere in the country,
drawn from the prior. The library computes and reports it, and chooses \(R\) by default to
hold it below \(10^{-6}\). This matters more than it sounds — at \(\varepsilon = 1\) and
\(R = 30\) the teleport probability is several percent, which would be a silent utility
disaster.

!!! note "Verified, not asserted"
    Both claims above are regression tests, not prose. The guarantee is checked by
    enumerating every \((x, x', y)\) triple on small generated graphs — a proof for each
    graph rather than evidence about it — and the test is mutation-checked: it catches a
    missing \(/2\) in the exponent, and it catches support-truncation-instead-of-capping.

## Keyed determinism

The uniform that drives the sampler is not random. It is

\[
u = \mathrm{HMAC\text{-}SHA256}(\text{key},\; \text{subject\_id} \,\|\, \text{postcode})
\]

mapped into \([0, 1)\). The same subject therefore always maps to the same output, with no
stored state. Repeated releases leak nothing further, and \(\varepsilon\) is spent once
however many times the pipeline runs — which also closes the averaging attack that
defeats naive per-call randomisation.

## Integer weights

Weights are quantised to `uint64` and the cumulative distribution is searched in integer
arithmetic, for two reasons.

**Floating-point leakage.** Mironov (CCS 2012) showed that naive floating-point
implementations of continuous DP mechanisms leak the true input through the low bits of
the IEEE representation. Our mechanism is already discrete over a finite set, so integer
weights make it immune by construction rather than defended by patching.

**Determinism.** The promise that a subject's output never changes would otherwise depend
on summation order, NumPy version and platform, and would break silently. Integer
weights make it bit-exact — and continuous integration runs the golden tests on both
Linux and macOS to prove it.
