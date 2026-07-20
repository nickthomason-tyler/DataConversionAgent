from conversion_agent.mapping.apply import apply, apply_typed, validate_proposals
from conversion_agent.mapping.model import CrosswalkWorkbook, Section, SourceRow
from conversion_agent.mapping.validation import validate_proposal_document


def _model() -> CrosswalkWorkbook:
    section = Section(
        tab="Permits",
        title="Type",
        src_cols=[1],
        dst_cols=[2],
        notes_col=3,
        header_row=1,
        rows=[SourceRow(row_idx=2, values=("Known",), existing=("",))],
        dest_lists=[["Allowed"]],
    )
    return CrosswalkWorkbook(path="input.xlsx", spec={"modules": {}}, sections=[section])


def test_reports_unknown_section_and_source_row() -> None:
    proposals = validate_proposal_document(
        {
            "proposals": [
                {"tab": "Other", "section": "Type", "source": ["Known"], "dest": ["Allowed"]},
                {"tab": "Permits", "section": "Type", "source": ["Unknown"], "dest": ["Allowed"]},
            ]
        }
    )

    report = apply_typed(_model(), proposals)

    assert report.accepted == ()
    assert [(rejection.source, rejection.reason) for rejection in report.rejected] == [
        (("Known",), "unknown section"),
        (("Unknown",), "unknown source row"),
    ]


def test_accepts_valid_proposal_and_rejects_already_mapped_source() -> None:
    model = _model()
    proposal = validate_proposal_document(
        {
            "proposals": [
                {"tab": "Permits", "section": "Type", "source": ["Known"], "dest": ["Allowed"]}
            ]
        }
    )

    accepted = apply_typed(model, proposal)
    rejected = apply_typed(model, proposal)

    assert accepted.accepted == proposal.proposals
    assert rejected.rejected[0].reason == "already mapped"


def test_validate_proposals_parses_the_external_payload_before_applying_it() -> None:
    report = validate_proposals(
        _model(),
        {
            "proposals": [
                {"tab": "Permits", "section": "Type", "source": ["Known"], "dest": ["Allowed"]}
            ]
        },
    )

    assert len(report.accepted) == 1


def test_legacy_apply_accepts_a_list_of_dicts_and_returns_legacy_report_shape() -> None:
    result = apply(
        _model(),
        [
            {"tab": "Permits", "section": "Type", "source": ["Known"], "dest": ["Allowed"]},
            {"tab": "Permits", "section": "Type", "source": ["Unknown"], "dest": ["Allowed"]},
        ],
    )

    assert result == {
        "accepted": 1,
        "no_good_match": 0,
        "rejected": [(["Unknown"], "unknown source row")],
    }
