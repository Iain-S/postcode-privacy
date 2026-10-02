# Why not just truncate?

The usual way to share postcodes safely is to cut them down: `LS2 9JT` becomes `LS2`, or
`LS2 9`. It is simple, it needs no key, and it is obviously coarse. So why do anything
more complicated?

## Truncation is not differential privacy. It is not any kind of privacy guarantee.

This is the central point, and it is not a matter of degree.

Truncation is **deterministic**. If your released value is `LS2`, then you are in `LS2`.
Not probably — certainly. An attacker learns a true fact about you with complete
confidence, and there is nothing you can say to deny it. The protection on offer is not
deniability but **crowd size**: the hope that the district contains enough other people
for you to be uninteresting.

A randomised mechanism is a different kind of object. When this library reports `LS6 1AA`
for you, that is evidence, not proof. Someone in `LS6` is more likely to produce it than
someone in `LS2`, but both can, and the ratio between those likelihoods is bounded by a
number you chose. You can always say *the mechanism did that, not me* — and the strength
of that denial is exactly \(\varepsilon\).

## Crowd size is wildly uneven, and worst where it is needed most

Truncation claims to treat everyone the same. It does not, and the gap is larger than
it is usually described. Measured across all 2,818 outward-code districts in the August
2026 build:

| residents per district | |
|---|---|
| smallest | **2** (PH30) |
| 1st percentile | 101 |
| median | 21,344 |
| 99th percentile | 77,018 |
| largest | 169,419 (CR0, Croydon) |

That is a factor of **764 between the 1st and 99th percentiles**, and roughly 85,000
between the extremes. The same operation is applied to everyone and the protection
delivered differs by nearly five orders of magnitude, with no way to measure the
difference from the released value, let alone control it.

![Histogram of residents per outward-code district on a log scale](figures/districts-light.svg#only-light){ loading=lazy }
![Histogram of residents per outward-code district on a log scale](figures/districts-dark.svg#only-dark){ loading=lazy }

### For nine districts, truncation does nothing at all

Nine outward codes contain exactly one postcode: `PA62`, `PA63`, `PA74`, `PH30`, `PH42`,
`PH43`, `PH44`, `TR22`, `TR23` — Mull and Iona, Corrour, the Small Isles, and the Isles
of Scilly.

For a resident of any of them, truncating the postcode to its outward code **discloses
the exact postcode unit**. The operation removes no information whatsoever. `PH30` goes
further: it is a single postcode with a census population of two.

Nobody intends this. It is what happens when a method has no quantity to check itself
against — there is no number truncation computes that would have flagged it.

Just under 1% of districts hold fewer than a hundred residents, and 871,823 people —
1.3% of the country — live in a district of fewer than five thousand.

### Against which, the mechanism

Measuring privacy in hops attacks this directly: a hop is a step to a neighbouring
postcode, and postcode units are roughly equally sized by construction, so a hop covers
a comparable number of people wherever you are. Measured at \(\varepsilon = 1\):

Self-probability — the chance the true postcode is handed back unchanged — measured
over 150 sampled postcodes per group:

| | p10 | median | p90 |
|---|---|---|---|
| urban | 0.911% | 2.541% | 4.261% |
| rural | 0.606% | 1.937% | 4.058% |

The medians differ by **1.31×**. More telling is that the spread *within* each group,
roughly fivefold from the tenth to the ninetieth percentile, is larger than the
difference *between* them — exposure depends more on your particular surroundings than
on whether those surroundings are a city or a glen.

Set that beside truncation's **764×** between the first and ninety-ninth percentile, and
its nine districts where a truncated postcode discloses the exact unit. Both sides are
measured.

!!! warning "A correction"
    An earlier version of this page gave the ratio as 1.03×, from a sample of 25
    postcodes per group. A second sample of 15 gave 2.1×. Two draws disagreeing that
    much meant the point estimate was never trustworthy, and it should not have been
    promoted to a headline on the strength of one sample. The figures above come from
    150 per group and are reported as a distribution for that reason.

The displacement in metres varies enormously — 0.49 km median urban against 2.62 km
rural — and that is the intended consequence, not a defect.

## The utility loss is uneven too, in the same direction

Rural districts are geographically enormous. Truncating a Highland postcode to its
district discards far more spatial information than truncating a London one — so the
rural resident loses the most analytical value *and* receives the least protection. The
trade is bad at both ends, for the same people.

## There is no dial

Truncation offers perhaps three settings: unit, sector, district. You cannot ask for
slightly more privacy, or trade a known amount of utility for a known amount of
protection, because there is no quantity to trade. \(\varepsilon\) is continuous, and it
can be [calibrated](getting-started.md#4-choose-an-epsilon) against a utility target you
actually care about.

## Auxiliary information is where truncation fails hardest

This is the argument that does the real work. Suppose an attacker knows your age, your
employer, and that you have an uncommon medical condition. Combine any of those with a
truncated postcode and the crowd that was supposed to hide you may collapse to one
person. Coarsening gives no guarantee about this, because it reasons about the released
field in isolation.

A differential privacy guarantee is **independent of auxiliary knowledge**. The bound on
the likelihood ratio holds whatever else the attacker knows — before, during or
afterwards. That property is the reason the formalism exists, and it is precisely the
property truncation lacks.

## Repeated releases

Release a truncated postcode twice and nothing changes, which is fine. Release a
*naively* randomised one twice and an attacker can average the draws and recover the
truth. This library avoids both failure modes by deriving the randomness from a keyed
function of the subject, so a person's output is fixed forever and \(\varepsilon\) is spent
once, however many times the pipeline runs.

## Where truncation is better

It would be dishonest to leave this out.

- **No key to manage.** Truncation has no secret, so it cannot leak one. This library's
  key, if compromised alongside the graph, allows exact inversion of every record.
- **Nobody is fooled.** `LS2` is visibly incomplete, so no downstream user mistakes it
  for an exact location. This library emits a *plausible real postcode*, and a careless
  analyst may treat it as the truth. That is a genuine hazard and it has to be managed by
  documentation and column naming.
- **Simplicity.** It needs no graph build, no parameter, and no explanation to an
  information governance panel that has not met \(\varepsilon\) before.

If your use case tolerates district-level resolution and you have no adversary model
worth the name, truncation is a reasonable choice and you should take it. The case for
this library is for when you need finer geography than a district, or need to say
something defensible about what an attacker can learn.
