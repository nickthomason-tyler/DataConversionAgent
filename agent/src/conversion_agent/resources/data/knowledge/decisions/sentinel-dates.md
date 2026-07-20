# Decision: sentinel date handling (1900-01-01 and 1753-01-01)

## Context

Legacy SQL Server systems commonly store 1900-01-01 (and occasionally
1753-01-01) as a stand-in for "no date". Loading these into the DCT as real
dates corrupts reporting and can violate EPL date-order validation
(e.g. issued before applied).

## Decision

Null the sentinel at the conformed layer and log every occurrence to the DQ
issue log under a dedicated rule (DQ-004 pattern). Do not silently drop the
row. If the column is required in the DCT (e.g. PERMIT_CASE.APPLIED_DATE),
the disposition is decided by the Client Data Steward per entity: derive from
an adjacent date (created date), or exclude the record from scope with
sign-off.

## Why

Sentinels are information ("the legacy system never captured this"), not
data. Preserving them as real dates hides that; dropping rows silently breaks
reconciliation counts.

## Applied on

Every SQL Server-sourced project. Oracle sources rarely exhibit this but the
DQ rule runs regardless.
