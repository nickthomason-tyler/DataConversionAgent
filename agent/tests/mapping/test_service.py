from pathlib import Path
from types import SimpleNamespace

import pytest

from conversion_agent.core.errors import WorkbookError
from conversion_agent.mapping import service
from conversion_agent.mapping import llm
from conversion_agent.mapping.llm import build_system_prompt
from conversion_agent.mapping.model import CrosswalkWorkbook, Section, SourceRow, WriteReport


def test_model_prompt_is_source_neutral_without_project() -> None:
    prompt = build_system_prompt(None)
    assert "legacy system" in prompt
    assert "New World" not in prompt


def test_model_prompt_uses_project_source_system() -> None:
    prompt = build_system_prompt("Legacy Alpha")
    assert "Legacy Alpha" in prompt


def test_deterministic_run_does_not_create_a_model_client(monkeypatch, tmp_path) -> None:
    model = CrosswalkWorkbook(
        path="input.xlsx",
        spec={"modules": {}},
        sections=[
            Section(
                tab="Permits",
                title="Type",
                src_cols=[1],
                dst_cols=[2],
                notes_col=None,
                header_row=1,
                rows=[SourceRow(row_idx=2, values=("Source",), existing=("",))],
                dest_lists=[["Source"]],
            )
        ],
    )

    monkeypatch.setattr(service, "load_validated_workbook", lambda path: model)
    monkeypatch.setattr(service.writeback, "write", lambda *args, **kwargs: {"auto": 1, "llm": 0})

    class FailingBackendFactory:
        def create(self) -> object:
            raise AssertionError("deterministic run must not create a model client")

    report = service.MappingService(backend_factory=FailingBackendFactory()).run(
        service.MappingRequest(input_path=Path("input.xlsx"), output_path=tmp_path / "output.xlsx")
    )

    assert report.deterministic == 1
    assert report.model_proposed == 0


def test_model_run_receives_the_selected_project_source_system(monkeypatch, tmp_path) -> None:
    model = CrosswalkWorkbook(
        path="input.xlsx",
        spec={"modules": {}},
        sections=[
            Section(
                tab="Permits",
                title="Type",
                src_cols=[1],
                dst_cols=[2],
                notes_col=None,
                header_row=1,
                rows=[SourceRow(row_idx=2, values=("Unknown",), existing=("",))],
                dest_lists=[["Allowed"]],
            )
        ],
    )
    client = object()
    seen: list[dict[str, object]] = []
    backend_factory = SimpleNamespace(
        create=lambda: client,
        model_id="test-model",
        settings=SimpleNamespace(backend_retries=2),
    )
    repository = SimpleNamespace(
        load=lambda _: SimpleNamespace(metadata=SimpleNamespace(source_system="Legacy Alpha"))
    )
    monkeypatch.setattr(service, "load_validated_workbook", lambda path: model)
    monkeypatch.setattr(service.writeback, "write", lambda *args, **kwargs: {"auto": 0, "llm": 0})
    monkeypatch.setattr(service.llm, "run", lambda section, **kwargs: seen.append(kwargs))

    service.MappingService(repository=repository, backend_factory=backend_factory).run(
        service.MappingRequest(
            input_path=Path("input.xlsx"),
            output_path=tmp_path / "output.xlsx",
            use_llm=True,
            project_id="alpha",
        )
    )

    assert seen == [
        {"client": client, "model_id": "test-model", "source_system": "Legacy Alpha", "retries": 2}
    ]


def test_model_run_accepts_the_legacy_positional_client() -> None:
    section = Section(
        tab="Permits",
        title="Type",
        src_cols=[1],
        dst_cols=[2],
        notes_col=None,
        header_row=1,
        rows=[SourceRow(row_idx=2, values=("Source",), existing=("",))],
        dest_lists=[["Allowed"]],
    )

    class Messages:
        def parse(self, **kwargs):
            return SimpleNamespace(
                parsed_output={
                    "mappings": [
                        {
                            "source": "Source",
                            "match": "Allowed",
                            "confidence": 0.9,
                            "rationale": "exact test match",
                        }
                    ]
                }
            )

    client = SimpleNamespace(messages=Messages())

    llm.run(section, client)

    assert section.proposals[2].dest == ("Allowed",)


def test_model_run_constructs_the_legacy_backend_client_when_omitted(monkeypatch) -> None:
    section = Section(
        tab="Permits",
        title="Type",
        src_cols=[1],
        dst_cols=[2],
        notes_col=None,
        header_row=1,
        rows=[SourceRow(row_idx=2, values=("Source",), existing=("",))],
        dest_lists=[["Allowed"]],
    )
    client = SimpleNamespace(
        messages=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(parsed_output={"mappings": [_mapping("Source")]})
        )
    )
    monkeypatch.setattr(llm.backend, "make_client", lambda: client)
    monkeypatch.setattr(llm.backend, "model_id", lambda: "legacy-model")

    llm.run(section)

    assert section.proposals[2].dest == ("Allowed",)


def test_build_report_surfaces_write_warnings() -> None:
    model = CrosswalkWorkbook(path="input.xlsx", spec={"modules": {}}, sections=[])

    report = service.build_report(
        model,
        WriteReport(
            deterministic_rows=0,
            model_rows=0,
            destination_cells=0,
            note_cells=0,
            warnings=("Style cloning disabled: ValueError: bad styles",),
        ),
    )

    assert report.warnings == ("Style cloning disabled: ValueError: bad styles",)


def _llm_section(*sources: str, candidates: list[str] | None = None) -> Section:
    return Section(
        tab="Permits",
        title="Type",
        src_cols=[1],
        dst_cols=[2],
        notes_col=None,
        header_row=1,
        rows=[
            SourceRow(row_idx=index + 2, values=(source,), existing=("",))
            for index, source in enumerate(sources)
        ],
        dest_lists=[candidates or ["Allowed", "Other"]],
    )


def _mapping(source: str, match: str | None = "Allowed", confidence: object = 0.9) -> dict:
    return {
        "source": source,
        "match": match,
        "confidence": confidence,
        "rationale": "test rationale",
    }


@pytest.mark.parametrize(
    "mappings",
    [
        [_mapping("A"), _mapping("A")],
        [_mapping("A")],
        [_mapping("A"), _mapping("Unknown")],
        [_mapping("A"), _mapping("B", "Not configured")],
        [_mapping("A"), _mapping("B", confidence=-0.1)],
        [_mapping("A"), _mapping("B", confidence=1.1)],
    ],
    ids=[
        "duplicate-source",
        "missing-source",
        "unknown-source",
        "destination-outside-candidates",
        "confidence-below-zero",
        "confidence-above-one",
    ],
)
def test_model_run_validates_the_complete_response_before_mutation(mappings: list[dict]) -> None:
    section = _llm_section("A", "B")
    client = SimpleNamespace(
        messages=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(parsed_output={"mappings": mappings})
        )
    )

    with pytest.raises(WorkbookError, match="Invalid model proposal batch"):
        llm.run(section, client)

    assert section.proposals == {}


def test_model_run_does_not_keep_an_earlier_batch_when_a_later_batch_is_invalid(
    monkeypatch,
) -> None:
    section = _llm_section("A", "B")
    responses = iter(
        [
            {"mappings": [_mapping("A")]},
            {"mappings": [_mapping("Unknown")]},
        ]
    )
    client = SimpleNamespace(
        messages=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(parsed_output=next(responses))
        )
    )
    monkeypatch.setattr(llm, "BATCH", 1)

    with pytest.raises(WorkbookError, match="Invalid model proposal batch"):
        llm.run(section, client)

    assert section.proposals == {}


def test_model_run_rejects_duplicate_pending_source_keys_before_request() -> None:
    section = _llm_section("Duplicate", "Duplicate")
    client = SimpleNamespace(
        messages=SimpleNamespace(
            parse=lambda **kwargs: pytest.fail("ambiguous source keys must not reach the backend")
        )
    )

    with pytest.raises(WorkbookError, match="unique pending sources"):
        llm.run(section, client)


def test_model_run_rejects_candidate_and_batch_limits_before_request(monkeypatch) -> None:
    client = SimpleNamespace(
        messages=SimpleNamespace(
            parse=lambda **kwargs: pytest.fail("invalid limits must not reach the backend")
        )
    )
    too_many_candidates = [f"Candidate {index}" for index in range(501)]

    with pytest.raises(WorkbookError, match="candidate limit"):
        llm.run(_llm_section("A", candidates=too_many_candidates), client)

    monkeypatch.setattr(llm, "BATCH", 41)
    with pytest.raises(WorkbookError, match="batch limit"):
        llm.run(_llm_section("A"), client)
