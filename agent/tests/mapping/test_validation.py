import openpyxl
import pytest

from conversion_agent.core.errors import WorkbookError
from conversion_agent.mapping.validation import load_validated_workbook
from conversion_agent.mapping.validation import validate_proposal_document


def test_rejects_duplicate_proposal_keys() -> None:
    payload = {
        "proposals": [
            {
                "tab": "Permits",
                "section": "Type",
                "source": ["A"],
                "dest": ["One"],
                "confidence": 0.8,
                "rationale": "first",
            },
            {
                "tab": "Permits",
                "section": "Type",
                "source": ["A"],
                "dest": ["Two"],
                "confidence": 0.7,
                "rationale": "second",
            },
        ]
    }
    with pytest.raises(WorkbookError, match="[Dd]uplicate"):
        validate_proposal_document(payload)


def test_rejects_workbook_without_lookup_spec(tmp_path) -> None:
    path = tmp_path / "invalid.xlsx"
    openpyxl.Workbook().save(path)
    with pytest.raises(WorkbookError, match="LookupSpec"):
        load_validated_workbook(path)


def test_wraps_a_corrupt_workbook_as_a_workbook_error(tmp_path) -> None:
    path = tmp_path / "corrupt.xlsx"
    path.write_bytes(b"not an XLSX archive")

    with pytest.raises(WorkbookError, match="Invalid workbook"):
        load_validated_workbook(path)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "proposals": [
                {
                    "tab": "Permits",
                    "section": "Type",
                    "source": ["A"],
                    "dest": ["One"],
                    "confidence": 1.1,
                }
            ]
        },
        {
            "proposals": [
                {
                    "tab": "Permits",
                    "section": "Type",
                    "source": ["A"],
                    "dest": ["One"],
                    "unexpected": True,
                }
            ]
        },
    ],
)
def test_rejects_invalid_proposal_schema(payload: object) -> None:
    with pytest.raises(WorkbookError, match="Invalid proposal document"):
        validate_proposal_document(payload)
