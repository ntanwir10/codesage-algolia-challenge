"""Algolia queries scoped to one repository use the filter form a live index honours"""

from app.services import algolia_service as algolia_module


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
