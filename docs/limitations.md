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

**The real fix** is to supply the missing information, which is what the
Geo-Graph-Indistinguishability work does by using a road network: you can only cross
water where a bridge exists. OS Open Roads is available under the Open Government Licence
and is the natural basis for a future version. The cost is that hop density would then
follow junction density rather than population, which is a different trade, not a free
improvement.

!!! note "Figure to come"
    A map of the affected edges around the Thames and Humber, with the size of the
    affected population, will be added once a full graph has been built.

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
