"""Algolia queries scoped to one repository use the filter form a live index honours"""

import json

from app.services import algolia_service as algolia_module
from app.services.code_parser import CodeParser, ParsedCodeEntity


def test_services_share_one_client_per_credentials(monkeypatch):
    # The real class, not the algolia_index fake; SearchClient.create opens no connection
    settings = algolia_module.settings
    monkeypatch.setattr(algolia_module, "_clients", {})
    first, second = algolia_module.AlgoliaService(), algolia_module.AlgoliaService()
    assert first.client is not None and first.client is second.client

    monkeypatch.setattr(settings, "algolia_admin_api_key", "another-test-key")
    assert algolia_module.AlgoliaService().client is not first.client


async def test_search_scopes_by_repository_with_a_numeric_filter(algolia_index):
    service = algolia_module.AlgoliaService()

    await service.search_code("debounce", repository_id=2, language="javascript")

    assert algolia_index.searches[-1]["filters"] == 'repository_id=2 AND language:"javascript"'


async def test_facet_values_cannot_add_filter_clauses(algolia_index):
    service = algolia_module.AlgoliaService()

    await service.search_code("x", repository_id=2, entity_type='function" OR repository_id=3 OR "')

    filters = algolia_index.searches[-1]["filters"]
    assert filters == 'repository_id=2 AND entity_type:"function\\" OR repository_id=3 OR \\""'


async def test_repository_stats_use_a_numeric_filter(algolia_index):
    await algolia_module.AlgoliaService().get_repository_stats(2)

    assert algolia_index.searches[-1]["filters"] == "repository_id=2"


async def test_delete_removes_only_that_repositorys_records(algolia_index):
    algolia_index.records = {
        "2_a": {"objectID": "2_a", "repository_id": 2},
        "3_b": {"objectID": "3_b", "repository_id": 3},
    }

    assert await algolia_module.AlgoliaService().delete_repository_index(2, wait=True)

    assert set(algolia_index.records) == {"3_b"}


class _PendingTask:
    """An indexing response whose task Algolia hasn't published"""

    def __init__(self, task_id):
        self.raw_responses = [{"taskID": task_id}]

    def wait(self):  # the v3 client's wait() would loop forever
        raise AssertionError("unbounded wait() must not be called")


async def test_settings_are_written_only_when_they_differ(algolia_index, monkeypatch):
    monkeypatch.setattr(algolia_module, "_configured_indexes", set())
    await algolia_module.AlgoliaService().setup_index_settings()
    assert algolia_index.settings_writes == 1

    # A new process with the settings already live writes nothing (and never waits)
    monkeypatch.setattr(algolia_module, "_configured_indexes", set())
    await algolia_module.AlgoliaService().setup_index_settings()
    assert algolia_index.settings_writes == 1


async def test_an_unpublished_delete_fails_instead_of_hanging(algolia_index, monkeypatch):
    monkeypatch.setattr(algolia_module, "DELETE_WAIT_SECONDS", 0.3)
    algolia_index.stuck_tasks = {7}
    monkeypatch.setattr(algolia_index, "delete_by", lambda params: _PendingTask(7))

    assert await algolia_module.AlgoliaService().delete_repository_index(2, wait=True) is False


async def test_an_unpublished_save_does_not_hang_indexing(algolia_index, monkeypatch):
    monkeypatch.setattr(algolia_module, "INDEX_WAIT_SECONDS", 0.3)
    algolia_index.stuck_tasks = {8}
    monkeypatch.setattr(algolia_index, "save_objects", lambda objects: _PendingTask(8))

    assert await algolia_module.AlgoliaService().index_documents([{"objectID": "a"}]) is True


async def test_settings_create_a_brand_new_index(algolia_index, monkeypatch):
    from algoliasearch.exceptions import RequestException

    def missing():
        raise RequestException("Index does not exist", 404)

    monkeypatch.setattr(algolia_module, "_configured_indexes", set())
    monkeypatch.setattr(algolia_index, "get_settings", missing)

    await algolia_module.AlgoliaService().setup_index_settings()

    assert algolia_index.settings_writes == 1
    assert algolia_index.settings == algolia_module.INDEX_SETTINGS


def record_bytes(record):
    return len(json.dumps(record, ensure_ascii=False).encode())


async def test_long_docstring_record_stays_under_the_size_limit(algolia_index):
    # A 9,000-character first docstring line used to make an ~11 KB record, failing the batch
    source = 'def f():\n    """' + "x" * 9000 + '"""\n    return 1\n'
    entity = next(e for e in CodeParser().parse("a.py", source, "python") if e.name == "f")

    record = algolia_module.AlgoliaService()._create_algolia_document(entity, 1, "a.py", "python")

    assert record_bytes(record) <= algolia_module.MAX_RECORD_BYTES
    assert len(record["description"]) == algolia_module.MAX_FIELD_CHARS


async def test_oversized_record_trims_content_to_fit(algolia_index):
    wide = "😀" * 600  # 4 bytes per character
    entity = ParsedCodeEntity(
        entity_type="function", name="f", description=wide, line_start=1, line_end=9,
        content=wide, body="😀" * 2000,
    )

    record = algolia_module.AlgoliaService()._create_algolia_document(entity, 1, "a.py", "python")

    assert record_bytes(record) <= algolia_module.MAX_RECORD_BYTES
    assert record["content"] and set(record["content"]) <= {"😀", "\n"}  # cut on a character boundary


async def test_indented_definitions_hold_their_signature_once(algolia_index):
    # tree-sitter strips the signature while the body keeps its indentation; Python keeps both
    js = "function outer() {\n  function inner(a) {\n    return a;\n  }\n}\n"
    py = "class A:\n    def m(self):\n        return 1\n"
    service = algolia_module.AlgoliaService()
    for path, source, language, name in (("a.js", js, "javascript", "inner"), ("a.py", py, "python", "m")):
        entity = next(e for e in CodeParser().parse(path, source, language) if e.name == name)

        record = service._create_algolia_document(entity, 1, path, language)

        assert record["content"].count(record["signature"].strip()) == 1, record["content"]
