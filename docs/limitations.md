# Limitations

Known defects and open problems, stated plainly. None of these is hidden elsewhere in the
documentation.

## The estuary shortcut

This is the most significant unfixed problem.

Delaunay triangulates the **convex hull** of the points, which means it fills concavities.
The Thames Estuary, the Bristol Channel, the Wash and Morecambe Bay are all concavities,
so the triangulation spans them — producing edges of twenty kilometres across open water
that the mechanism treats as **one hop**, identical to your literal next-door neighbour.

For residents near such an edge, the output distribution has a tail that nobody else's
has: they may be reported across the water as readily as across the street. The guarantee
still holds — any graph gives a valid metric — but the *meaning* of a hop degrades
locally, and that is a real defect.

**Why it is not simply fixed.** Water and empty moorland are the same object in a point
set: a gap with nothing in it. No purely geometric criterion separates the Solent from
Dartmoor. A length threshold cannot, and neither can the parameter-free alternatives —
Gabriel and relative-neighbourhood graphs keep an estuary-spanning edge for exactly the
same reason, because the disc or lune over the water contains no points. **The information
needed is not in the data.**

An adaptive length heuristic is implemented and tested, but it is **off by default**,
because it is a guess with no ground truth to tune against.

**The real fix** needs the missing information, and the obvious candidate — replacing
the graph with a road network, as the Geo-Graph-Indistinguishability work does — is
less attractive here than it first appears.

In this library the nodes *are* postcodes, so one hop means "one postcode over", which
is close to "about fifteen households over" because small-user postcodes are roughly
equal-sized by construction. That is precisely why exposure comes out flat across urban
and rural in the table above. On a road network the nodes are junctions, so hop count
tracks junction density rather than population — and a cul-de-sac estate and an empty
moorland road have junction densities unrelated to how many people live along them.
Replacing the graph would risk the one property that has been measured and shown to
work.

The better use of road data is to **prune rather than replace**: keep postcodes as
nodes, and delete the Delaunay edges that do not correspond to a feasible short journey.
The most promising test is a *detour ratio* — road distance divided by straight-line
distance — because it is a measurement rather than a classification, and it is exactly
what separates an estuary from a moor. Across the moor the straight line is walkable;
across the estuary the detour to the nearest bridge is enormous. It would also catch
railway cuttings, uncrossable motorways and military ranges without naming any of them.

### Measured

At \(\varepsilon = 1\), twenty-five sampled postcodes per group, on the August 2026
build of 1,725,511 nodes:

| group | median | p95 | same LSOA | self-probability |
|---|---|---|---|---|
| urban | 0.49 km | 9.86 km | 28.9% | 2.27% |
| rural | 2.62 km | 260.27 km | 26.6% | 2.20% |

Read the last two columns first, because they are the design working. Exposure is
effectively equal — a postcode is handed back unchanged about as often in Sutherland as
in Leeds, across a four-order-of-magnitude difference in how much ground a postcode
covers. That is the whole claim the hop metric makes.

The rural **p95 of 260 km** is the defect, and it is worth being careful about its
cause. Rural sparsity alone is the design behaving correctly — if there are few
postcodes nearby, the nearest ones genuinely are far away. The long tail is something
else, and the measurement below narrows it down.

### The floor no graph can fix

A measurement on the Isle of Lewis gave a median displacement of 308 km. It is tempting
to read that as a bug, and it is worth being clear that it is not.

That number is the mechanism honestly reporting that **there are not many people near a
Lewis resident**. Remove the sea-crossing edges and Lewis becomes its own component,
where a resident is hidden among a few thousand island postcodes instead of being sent
to the mainland. That is not better privacy — it is the same limited privacy, now
visible rather than disguised as a long journey.

Island and remote residents face a genuine privacy–utility floor, because it is a
property of where people live rather than of the edges we draw. No graph construction
removes it. What a better graph would do is make it *visible*, which is an argument for
fixing the artefact, not for pretending the floor is not there.

!!! note "Figure to come"
    A map of the affected edges around the Thames and Humber, with the number of
    postcodes touching one, will be added once the measurement is complete.

## People who move house

The randomness is keyed on `(subject_id, postcode)`. A subject who moves therefore gets an
independently drawn new output, which costs a second \(\varepsilon\) and whose relationship
to the first leaks information about the move having happened.

Keying on `subject_id` alone instead would correlate the two outputs through a shared
quantile, which has its own disclosure problem. Neither option is free. Version 1 takes
the former and documents it here; a proper treatment needs a sequential-release analysis.

## Key compromise is total

Anyone holding both the key and the graph artefact can invert the perturbation exactly
and recover every true postcode. The key is not a convenience; it is as sensitive as the
source dataset and must be handled that way.

## The output looks exact

The mechanism emits a plausible real postcode. A downstream analyst who has not read this
page may reasonably mistake it for the true value. Name the output column so that it
cannot be confused — the CLI defaults to `postcode_dp` for this reason — and say so in
whatever data dictionary travels with the release.

## Northern Ireland

ONSPD's Northern Ireland records are licensed from Land & Property Services and may not
be redistributed, so any artefact you intend to share must be built with `--gb-only`.
Separately, no Northern Ireland population source has been incorporated, so the
population prior falls back to uniform there.

## Coverage of the population prior

England and Wales use 2021 Census Output Area populations, split evenly across the
postcodes in each area. Scotland uses the National Records of Scotland per-postcode
figures, which are finer. The prior is therefore of **mixed resolution** across the
United Kingdom. The guarantee is unaffected — any prior is admissible — but utility
comparisons between nations should be read with this in mind.

## Aggregate statistics are out of scope

This library perturbs individual postcodes. It does not produce differentially private
counts or statistics by geography. That is a related but separate problem requiring
different machinery, and combining a per-record mechanism with aggregate release needs
a composition analysis this library does not provide.
