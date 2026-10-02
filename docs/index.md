# postcode-privacy

Differential privacy for UK postcodes, measured in **graph hops rather than metres**.

Given a person's real postcode, this library emits a different *real* postcode, such that
the true one is deniable under a formal guarantee:

!!! abstract "The guarantee"
    Two postcodes \(h\) hops apart produce outputs whose likelihoods differ by at most
    \(e^{\varepsilon h}\).

!!! warning "Pre-alpha"
    Nothing here works yet. The command lines on this site describe the intended
    interface; they do not run. No figure on this site is a placeholder — where a figure
    is missing, it is because the number behind it does not exist yet.

## The problem

A postcode unit is a delivery round, not a point, and its real-world size varies by four
orders of magnitude — a single tower block in central Glasgow, several square kilometres
in Sutherland. Privacy measured in metres therefore treats those two residents as though
they were alike, when they are not. The Glaswegian is hidden among thousands of
neighbours within 200 m; the Sutherland resident may be the only household for a mile.
The same \(\varepsilon\) is claimed for both, and it means something very different to each.

The existing options are worse. Dropping the postcode destroys geographic analysis.
Rounding coordinates is trivially invertible. Truncating to the outward code has no
formal guarantee at all, and its protection is wildly uneven in exactly the way described
above — see [Why not just truncate?](why-not-truncation.md).

![Relief map of Great Britain beside a map of residents per 5 km cell](figures/density-light.png#only-light){ loading=lazy }
![Relief map of Great Britain beside a map of residents per 5 km cell](figures/density-dark.png#only-dark){ loading=lazy }

<figcaption markdown>Population is as uneven as the ground it sits on. Any method that treats every postcode alike is treating these two maps as though they were flat.</figcaption>

## The approach

Postcode units become the nodes of a graph, with edges joining geographic neighbours.
Privacy is then measured in **hops** along that graph, not in metres.

Density adaptation comes for free. Three hops is roughly 200 m in central Leeds and
roughly 6 km on Bodmin Moor, which is the correct behaviour — because the question that
determines your risk is *how many other people could I be?*, not *how many metres away
am I?*.

## Credit

**The central idea is not ours.** Measuring metric differential privacy by shortest-path
distance on a graph, rather than by Euclidean distance, is
**Geo-Graph-Indistinguishability**, due to Shun Takagi, Yang Cao, Yasuhito Asano and
Masatoshi Yoshikawa ([arXiv:2010.13449](https://arxiv.org/abs/2010.13449); DBSec 2019),
who also give the Graph-Exponential Mechanism. It rests in turn on metric differential
privacy (Chatzikokolakis et al., PETS 2013) and geo-indistinguishability (Andrés et al.,
CCS 2013).

In one sentence, this library is **GG-I applied to UK postcodes**. What it adds is
narrow and is listed honestly on the [References](references.md) page.

## What you get

- A **real postcode** as output, not a coordinate or a redacted field, so downstream
  joins and lookups keep working.
- **Keyed determinism** — the same person always maps to the same output, so repeated
  releases leak nothing further and \(\varepsilon\) is spent once.
- A **population-weighted prior**, so outputs land where people actually live.
- Exact sampling with **no floating-point weights**, closing a known leakage channel in
  DP implementations.

## Where to go next

- [Getting started](getting-started.md) — install, build a graph, perturb a file.
- [Why not just truncate?](why-not-truncation.md) — the comparison that matters most.
- [How it works](how-it-works.md) — the guarantee, and why the radius cap is sound.
- [Limitations](limitations.md) — including a known defect we have not fixed.
