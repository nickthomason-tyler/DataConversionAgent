"""Apply externally produced mapping proposals through the validation gate."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Proposal
from .validation import (
    ProposalDocument,
    ProposalInput,
    validate_proposal_document,
)


@dataclass(frozen=True)
class ProposalRejection:
    source: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ProposalApplicationReport:
    accepted: tuple[ProposalInput, ...]
    no_match: tuple[ProposalInput, ...]
    rejected: tuple[ProposalRejection, ...]


def apply_typed(model, proposals: ProposalDocument) -> ProposalApplicationReport:
    """Validate proposals against workbook rows without overwriting mappings."""
    accepted: list[ProposalInput] = []
    no_match: list[ProposalInput] = []
    rejected: list[ProposalRejection] = []
    sections = {(section.tab, section.title): section for section in model.sections}

    for proposal in proposals.proposals:
        section = sections.get((proposal.tab, proposal.section))
        if section is None:
            rejected.append(ProposalRejection(proposal.source, "unknown section"))
            continue

        rows = [row for row in section.rows if row.values == proposal.source]
        if not rows:
            rejected.append(ProposalRejection(proposal.source, "unknown source row"))
            continue

        for row in rows:
            if any(value.strip() for value in row.existing) or row.row_idx in section.proposals:
                rejected.append(ProposalRejection(proposal.source, "already mapped"))
                continue

            if proposal.dest is None:
                section.proposals[row.row_idx] = Proposal(
                    dest=tuple("" for _ in section.dst_cols),
                    method="llm",
                    confidence=proposal.confidence,
                    note=f"NO GOOD MATCH — {proposal.rationale[:180]}",
                )
                no_match.append(proposal)
                continue

            if len(proposal.dest) != len(section.dst_cols):
                rejected.append(ProposalRejection(proposal.source, "wrong destination arity"))
                continue
            if not section.dest_lists or not all(
                value in valid for value, valid in zip(proposal.dest, section.dest_lists)
            ):
                rejected.append(ProposalRejection(proposal.source, "value not in pick list"))
                continue
            if (
                len(proposal.dest) == 2
                and section.cascade
                and proposal.dest[1] not in section.cascade.get(proposal.dest[0], [])
            ):
                rejected.append(ProposalRejection(proposal.source, "cascade violation"))
                continue

            section.proposals[row.row_idx] = Proposal(
                dest=proposal.dest,
                method="llm",
                confidence=proposal.confidence,
                note=f"proposed ({proposal.confidence:.0%}): {proposal.rationale[:180]}",
            )
            accepted.append(proposal)

    return ProposalApplicationReport(tuple(accepted), tuple(no_match), tuple(rejected))


def apply(model, proposals: list[dict]) -> dict:
    """Legacy list-of-dicts entry point retained for direct Python callers."""
    report = apply_typed(model, validate_proposal_document({"proposals": proposals}))
    return {
        "accepted": len(report.accepted),
        "no_good_match": len(report.no_match),
        "rejected": [(list(rejection.source), rejection.reason) for rejection in report.rejected],
    }


def validate_proposals(model, payload: object) -> ProposalApplicationReport:
    """Parse and validate an external payload against a workbook model."""
    return apply_typed(model, validate_proposal_document(payload))


def main(argv=None) -> int:
    """Compatibility entry point for ``python -m conversion_agent.mapping.apply``."""
    from conversion_agent.cli.apply import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
