# References

Work this library builds on. Where an idea here is someone else's, this is where the
credit belongs; the README and the design spec both point at this file.

## The core privacy notion is not ours

**Metric differential privacy** — the generalisation of DP to an arbitrary metric on the
secret space, which is what makes hop distance a legitimate basis for a guarantee.

> Konstantinos Chatzikokolakis, Miguel E. Andrés, Nicolás Emilio Bordenabe, Catuscia
> Palamidessi. *Broadening the Scope of Differential Privacy Using Metrics.* PETS 2013.

**Geo-indistinguishability** — metric DP applied to location, with ε per metre on the
Euclidean plane. The approach this library deliberately departs from.

> Miguel E. Andrés, Nicolás E. Bordenabe, Konstantinos Chatzikokolakis, Catuscia
> Palamidessi. *Geo-Indistinguishability: Differential Privacy for Location-Based
> Systems.* ACM CCS 2013.

**Geo-Graph-Indistinguishability (GG-I)** — metric DP using shortest-path distance on a
*graph* rather than Euclidean distance, together with the Graph-Exponential Mechanism
(GEM). **This is the idea at the centre of this library, and it is theirs, not ours.**

> Shun Takagi, Yang Cao, Yasuhito Asano, Masatoshi Yoshikawa.
> *Geo-Graph-Indistinguishability: Protecting Location Privacy for LBS over Road
> Networks.* DBSec 2019.
>
> Shun Takagi, Yang Cao, Yasuhito Asano, Masatoshi Yoshikawa.
> *Geo-Graph-Indistinguishability: Location Privacy on Road Networks Based on
> Differential Privacy.* arXiv:2010.13449, 26 October 2020.

Their motivation is also the rigorous form of the argument for using a graph at all:
Euclidean geo-indistinguishability *overstates* the privacy it delivers, because a real
adversary knows the network and discounts outputs that are not reachable.

Their graph is a road network, which handles water correctly and without a parameter,
since a crossing exists only where a bridge does. That remains the principled answer to
the estuary-shortcut problem this library currently leaves open.

**The exponential mechanism** itself:

> Frank McSherry, Kunal Talwar. *Mechanism Design via Differential Privacy.* FOCS 2007.

## What this library adds

Stated narrowly and honestly, against the above:

1. **UK postcode units as the secret space**, with the graph derived from ONSPD
   centroids rather than a road network.
2. **A population-weighted prior**, so outputs land where people actually live.
3. **The capped metric `min(d, R)`**, which keeps the mechanism exactly computable over
   ~1.7M nodes while remaining pure DP. Takagi et al. address scalability differently —
   by a greedy approximation to an optimisation problem — rather than by truncating the
   mechanism, so this appears to be distinct. *This must be confirmed by reading both
   papers in full before the methods note claims it.*
4. **Keyed-deterministic perturbation**, so repeated releases of one subject cost one ε.
5. **Integer weights**, closing the floating-point leakage channel.

None of these is the graph idea. If a single sentence is needed: *this is GG-I applied to
UK postcodes, with an exactly-computable capped metric and a keyed deterministic
sampler.*

## Supporting results

**Floating-point leakage in DP implementations** — why the weights here are integers.

> Ilya Mironov. *On Significance of the Least Significant Bits in Differential Privacy.*
> ACM CCS 2012.

**α-shapes and χ-shapes** — the computational-geometry lineage of the opt-in pruning
heuristic. The project's `alpha` is a locally-adaptive variant of this family; it is not
a term of art, and it is off by default.

> Herbert Edelsbrunner, David G. Kirkpatrick, Raimund Seidel. *On the Shape of a Set of
> Points in the Plane.* IEEE Transactions on Information Theory, 1983.
>
> Matt Duckham, Lars Kulik, Mike Worboys, Antony Galton. *Efficient Generation of Simple
> Polygons for Characterizing the Shape of a Set of Points in the Plane.* Pattern
> Recognition, 2008.

## Data sources

- **ONS Postcode Directory (ONSPD)**, ONS Open Geography Portal. Great Britain records
  are available under the Open Government Licence v3. Northern Ireland records are
  licensed from Land & Property Services and **may not be redistributed**.
- **Census 2021 Output Area population estimates**, ONS, Open Government Licence v3.
- **OS Open Roads**, Ordnance Survey, Open Government Licence v3 — not used in v1; the
  candidate basis for a road-network graph.
