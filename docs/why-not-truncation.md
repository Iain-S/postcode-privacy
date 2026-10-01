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

Truncation claims to treat everyone the same. It does not.

A postcode district in central London may contain tens of thousands of residents. A rural
district in the Highlands may contain a few hundred, spread over hundreds of square
kilometres. Truncating both to the district applies the same *operation* and delivers
radically different *protection* — by orders of magnitude — while offering no way to
measure the difference, let alone control it.

Measuring privacy in hops attacks this directly: a hop is a step to a neighbouring
postcode, so it covers a comparable number of people wherever you are. The displacement
in metres varies enormously; the exposure does not.

!!! note "Figure to come"
    The chart that settles this is crowd size — the number of residents sharing your
    released value — for truncation and for this mechanism, split by urban and rural.
    It will be generated from the August 2026 ONSPD build once the mechanism is
    implemented. It is not shown here because the numbers do not exist yet, and a
    privacy library is the last place an illustrative figure belongs.

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
