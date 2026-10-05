# Security policy

## Reporting

Please report suspected vulnerabilities through GitHub's private vulnerability
reporting on this repository, rather than opening a public issue.

A privacy flaw here is not an ordinary bug. If the mechanism leaks more than it claims,
data already released under it cannot be recalled, so the useful report is the one that
arrives before anyone else notices.

## What counts as a vulnerability

Anything that makes the released guarantee untrue, including:

- an input pair and output for which the likelihood ratio exceeds
  `exp(epsilon * d)` — a counterexample is the most valuable report possible
- a path where a subject's output depends on anything other than the key, the subject
  identifier and the true postcode
- key material reaching a log, a traceback, an error message or a file written with
  permissions wider than `0400`
- a build that ships postcode data, which is a licensing breach as well as a size problem

## What does not

- An attacker succeeding when they already knew enough. Differential privacy bounds what
  the *release* adds, not what the adversary brought with them. A resident of a
  two-person postcode district is identifiable whatever this library does.
- Loss of utility. Outputs landing far from the truth is the mechanism working.

## Status

Pre-alpha, and unaudited. There are tests, mutation checks and cross-platform golden
outputs, but no external review has taken place. Treat the guarantee as unverified by
anyone but its author until that changes.
