from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog
from conversion_agent.resources.knowledge import KnowledgeIndex


def test_project_overlay_is_scoped_and_cited(project_root) -> None:
    overlay = project_root / "alpha" / "knowledge"
    overlay.mkdir()
    (overlay / "alpha-rule.md").write_text(
        "# Alpha rule\n\nUse ALPHA-ONLY disposition.", encoding="utf-8"
    )
    project = FilesystemProjectRepository(project_root).load("alpha")
    index = KnowledgeIndex.for_project(ResourceCatalog().shared_knowledge(), project)
    hit = index.search("ALPHA-ONLY", top_k=1)[0]
    assert hit.scope == "project"
    assert hit.citation == "[project source: alpha/knowledge/alpha-rule.md § Alpha rule]"


def test_dictionary_is_cached_and_contains_release_metadata() -> None:
    catalog = ResourceCatalog()
    first = catalog.dictionary()
    second = catalog.dictionary()
    assert first is second
    assert first["version"] == "V2025.2.01"
    assert first["table_count"] == 309
