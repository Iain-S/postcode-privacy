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

### What GG-I does and does not cover

Read in full rather than from the abstract, because the distinction decides what this
library may claim.

Their secret space is the set of **road-network junctions**, and their metric is
shortest path **weighted by road segment length** — effectively metres along roads. The
Graph-Exponential Mechanism is

> `Pr(GEM(v) = o) = α(v) · exp(−ε/2 · d_s(v, o))`, with `α(v)` the normaliser.

the same exponential form this library uses, with no prior term: their user prior `πu`
appears only inside an optimisation objective, never in the mechanism.

They impose **no cap and no truncation**. The paper notes that sampling becomes
difficult when the vertex count is large and points at consistent weighted sampling, but
GEM itself is unmodified. Their answer to tractability is a greedy algorithm that shrinks
the *output range* `W` — which vertices may be emitted at all — subject to a utility
constraint. That is a **global** restriction, identical for every input, so it preserves
the guarantee; it is a different solution from capping the metric, not the same one.

Repeated releases, composition and trajectories are explicitly out of scope: "a user
sends the location once". Floating-point arithmetic is not discussed. Their evaluation
graphs have 168 and 1,155 nodes, with synthetic lattices up to about 5,000.

**The exponential mechanism** itself:

> Frank McSherry, Kunal Talwar. *Mechanism Design via Differential Privacy.* FOCS 2007.

## What this library adds

Stated narrowly and honestly, against the above:

1. **Hop count over postcode units**, rather than weighted road distance over
   junctions. This is the substantive departure. Road distance in metres still gives a
   Sutherland resident far weaker protection than a Glaswegian for the same ε, because
   their nearest neighbour genuinely is further away. Counting hops between
   roughly equally-sized postcode units equalises *exposure* instead of distance —
   measured here at a self-probability of 2.20% rural against 2.27% urban.
2. **A population-weighted prior inside the mechanism**, so outputs land where people
   actually live. GEM has no prior term.
3. **The capped metric `min(d, R)`**, which keeps the mechanism exactly computable over
   1.7M nodes while remaining pure DP. Takagi et al. impose no cap and leave large-graph
   sampling as an open difficulty; their greedy algorithm shrinks the global output
   range instead, which is a different device. Their largest real graph has 1,155 nodes.
4. **Keyed-deterministic perturbation**, so repeated releases of one subject cost one ε.
   Repeated release is explicitly out of scope in their work.
5. **Integer weights**, closing the floating-point leakage channel. Not discussed there.

None of these is the graph idea, which is theirs. If a single sentence is needed:
*this is GG-I applied to UK postcodes, with hop count in place of road distance, an
exactly-computable capped metric, and a keyed deterministic sampler.*

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
