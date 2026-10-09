# Threat model

The theorem in [Methods](methods.md) is about an abstract mechanism that draws fresh
randomness. The library draws nothing: every output is a deterministic function of a
secret key. That is a deliberate design choice — it is what makes repeated publication
safe — but it changes what is being claimed, and this page states the change precisely.

## The guarantee is computational, not information-theoretic

The mechanism's uniform is

\[
u \;=\; \mathrm{HMAC\text{-}SHA256}\bigl(k,\; \text{subject\_id} \,\|\, 0\mathrm{x}00 \,\|\, \text{postcode}\bigr),
\]

reduced into range by rejection. For a fixed key \(k\) the map from input to output is a
function, not a distribution. The randomness that the proof quantifies over is the
**uniform choice of \(k\)**, and the step from "HMAC output" to "uniform draw" is the
assumption that HMAC-SHA256 is a pseudorandom function.

Stated as an experiment. Fix a graph \(G\), an \(\varepsilon\), a radius \(R\), and two
postcodes \(x, x'\) at capped distance \(h\). A distinguisher \(\mathcal{A}\) running in
time \(t\) is given one output, produced either from \(x\) or from \(x'\) by the shipped
implementation under a key drawn uniformly from \(\{0,1\}^{256}\), and may query the
implementation on any other `(subject_id, postcode)` pairs of its choosing under the
same key. Write \(p_x\) for the probability it answers "\(x\)". Then

\[
p_x \;\le\; e^{\varepsilon h}\, p_{x'} \;+\; \mathrm{Adv}^{\mathrm{prf}}_{\mathrm{HMAC}}(t, q),
\]

where \(q\) is the number of queries. Replace HMAC by a truly random function and the
advantage term vanishes, leaving exactly the inequality proved in Methods: the ideal
mechanism's guarantee is information-theoretic, and the shipped one inherits it up to
the PRF advantage. For HMAC-SHA256 with a 256-bit key that term is not a practical
concern, but it is not zero, and a document claiming unconditional differential privacy
for this implementation would be wrong.

Two consequences worth stating plainly:

- **A distinguisher who holds the key has no guarantee at all.** The bound above is
  vacuous when \(\mathrm{Adv}^{\mathrm{prf}} = 1\), which is what holding \(k\) gives.
  See [Key compromise](#what-key-compromise-actually-gives-an-attacker) below.
- **Key quality is part of the guarantee.** `Key.generate()` and `postcode-privacy
  keygen` use the operating system's CSPRNG. A key derived from a passphrase, a
  timestamp, or anything else guessable narrows the key space and the bound degrades
  with it.

## When repeated releases count as one observation

The claim "repeated releases leak nothing further" is a statement about *identical*
inputs, and it is exactly true under exactly these conditions. Every one of them must
hold:

| must be unchanged | why |
|---|---|
| the key \(k\) | a different key is an independent draw |
| the subject identifier | the identifier is hashed; a different one is a different draw |
| the true postcode | the postcode is hashed too, so a move is a second draw |
| the graph artefact | node ordering and the prior both feed the output; cite `graph_sha256` |
| \(\varepsilon\) and the radius | both enter the weights |
| the library's output-stability version | see [CHANGELOG](https://github.com/Iain-S/postcode-privacy/blob/main/CHANGELOG.md) |

When all six match, the second release is *byte-identical* to the first and an adversary
who already holds the first learns nothing — not "little", nothing. There is no
composition to bound because there is only one observation.

When any of them differs, the two releases are two draws and the privacy loss composes
in the ordinary way: an adversary seeing both has, in the worst case, two independent
observations of the same secret, so the guarantee degrades to \(2\varepsilon\tilde d\).
Sequential composition of metric DP is the relevant bound, and nothing in the library
tracks or enforces a budget across runs. The measured consequence of getting this wrong
is in [Methods](methods.md#keyed-determinism): twenty independent draws of one subject
take a Bayesian adversary from 2/20 exact identifications to 18/20.

In particular:

- **Rotating the key re-perturbs everyone.** It is a new release of the same people at a
  second \(\varepsilon\), not a refresh. Key rotation is a privacy *cost* here, and that
  is the opposite of the usual advice. Rotate on compromise, and treat the old and new
  releases as a pair.
- **Rebuilding the graph re-perturbs everyone**, including a rebuild from the same ONSPD
  with a different population file. This is why the artefact's own hash is recorded.
- **A minor version bump re-perturbs everyone**, which is why output stability is in the
  version number.

## Subject identifiers are part of the security boundary

The identifier is an input to the keyed function, so its properties become privacy
properties.

- **It must be stable.** If a subject's identifier changes between releases, they are
  perturbed again and \(\varepsilon\) is spent twice. Row numbers, timestamps, and
  anything regenerated per export are unsuitable. The CLI validates that every row has
  an identifier and reports failures by row number, but it cannot tell a stable
  identifier from an unstable one.
- **It must be unique per person.** Two different people sharing an identifier at the
  same postcode receive the same output, which correlates them. Two rows for the *same*
  person sharing an identifier is the intended case.
- **It need not be secret, and should not be sensitive.** The identifier is not
  published by the mechanism, but it is hashed with the postcode, so a predictable
  identifier does not weaken anything on its own. Choose a pseudonymous key rather than
  a name or an NHS number, for the ordinary reasons.
- **The same identifier under two keys is two draws.** See the table above.

## What key compromise actually gives an attacker

Earlier versions of this documentation said an attacker holding the key and the graph
could "invert every perturbation exactly". That is too strong, and the accurate version
is barely less alarming.

With \(k\) and the graph, an attacker can evaluate the mechanism themselves. For an
observed output \(y\) attached to a known subject \(s\), they compute the candidate set

\[
\mathcal{C}(s, y) \;=\; \{\, x \in V \;:\; f_k(s, x) = y \,\},
\]

by evaluating \(f_k(s, \cdot)\) over the country. Every postcode outside
\(\mathcal{C}(s, y)\) is eliminated with certainty — not made unlikely, eliminated. The
guarantee is gone: it was conditional on \(k\) being unknown.

What is *not* guaranteed is that \(\mathcal{C}(s, y)\) is a single postcode. The map is
not injective, and collisions are ordinary. Measured on the August 2026 national graph at
\(\varepsilon = 1\) with the subject fixed, taking 60 randomly chosen outputs and
searching only the 203 postcodes within six hops of each:

| postcodes found mapping to the output | outputs |
|---|---|
| 0 | 20 |
| 1 | 27 |
| 2 | 10 |
| 3 | 2 |
| 4 | 1 |

Two-thirds of outputs had at least one nearby postcode mapping to them, with a mean of
0.95 and a maximum of 4 — and these are *lower bounds* on \(|\mathcal{C}(s, y)|\),
because the search covered a six-hop neighbourhood rather than the country, and a
candidate can lie anywhere: the metric is capped, not the support.

The practical reading: key compromise should be treated as full disclosure of the source
postcodes. The residual ambiguity is real but small, it is not a designed protection,
and it evaporates against an attacker with any auxiliary knowledge — a partial postcode,
a town, a list of the sites in the study. Store the key as you store the source dataset.

## Where this sits against the ICO's guidance

The Information Commissioner's Office addresses differential privacy directly in its
guidance on
[privacy-enhancing technologies](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/privacy-enhancing-technologies/what-pets-are-there/differential-privacy/).
Two points from it bear on this library, and neither is a clean endorsement.

**DP can contribute to anonymisation, conditionally.** The ICO's position is that
differential privacy can render information anonymous where an appropriate level of
noise makes the risk of re-identification sufficiently remote — a judgement about the
noise level *and* the release context together, not a property conferred by using a DP
mechanism at all. An \(\varepsilon\) chosen for utility does not inherit that judgement.
The numbers in [Methods](methods.md#keyed-determinism) show \(\varepsilon = 2\) already
allowing a Bayesian adversary to pinpoint one subject in ten from a single release;
whether any particular \(\varepsilon\) makes re-identification "sufficiently remote" for
your release is a decision for your data protection officer, informed by the
`postcode-privacy report` and `evaluate` output, and this library does not make it for
you.

**Local DP protects record content, not record association.** That is the ICO's own
distinction and it applies squarely here. This is a *local* mechanism: it protects the
postcode field. It does not hide that a record exists, that a particular subject is in
the dataset, or anything carried in the other columns. A release whose remaining columns
identify people is not anonymised by perturbing the postcode, and the output column's
plausibility can make that easier to overlook rather than harder.

Nothing on this page is legal advice.
