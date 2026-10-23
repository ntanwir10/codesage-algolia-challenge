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
