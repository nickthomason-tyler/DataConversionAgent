# Decision: duplicate contact survivorship

## Context

Legacy systems accumulate duplicate person/company records (same human, many
rows). The DCT expects one CONTACT per real-world party, linked to many
cases.

## Decision

Dedupe at the conformed layer on a match key of normalized name + address
(configurable per project), keeping the most recently active record as the
survivor and re-pointing all case links to it. Merged-away legacy keys are
recorded in a merge map table so reconciliation can explain every "missing"
row, and the merge map ships to the client with each mock cycle.

## Why

Deduping without a merge map makes row-count reconciliation impossible to
sign off; deduping at extract or staging destroys the audit trail.

## Applied on

All projects converting contacts. Threshold tuning (strict vs fuzzy match)
is a per-client decision recorded in the project file.
