from test_validation import candidate


def test_dedup_discards_paraphrase_but_preserves_distinct_query():
    from webshaper.export import deduplicate
    a = candidate()
    b = a.model_copy(deep=True)
    b.task.task_id, b.task.question = "paraphrase", "A paraphrase asking the identical structured question."
    b.seed_id = "different_seed"
    kept, dropped = deduplicate([a, b])
    assert [c.task.task_id for c in kept] == ["task"]
    assert dropped[0]["reason_codes"] == ["duplicate_query_answer"]


def test_lineages_answers_and_duplicate_sources_stay_in_same_partition():
    from webshaper.export import partitions
    a = candidate()
    b = a.model_copy(deep=True)
    b.task.task_id, b.answer = "descendant", ["b"]
    c = a.model_copy(deep=True)
    c.task.task_id, c.seed_id, c.answer = "other", "other_seed", ["c"]
    source_groups = {"task": {"page1"}, "descendant": {"page2"}, "other": {"page2"}}
    result = partitions([a, b, c], source_groups)
    assert result["task"] == result["descendant"] == result["other"]


def test_reference_conflict_rejects_both_copies():
    from webshaper.export import deduplicate
    a = candidate()
    b = a.model_copy(deep=True)
    b.task.task_id, b.answer = "conflict", ["b"]
    kept, dropped = deduplicate([a, b])
    assert kept == []
    assert len(dropped) == 2


def test_canonical_union_does_not_permute_unrelated_branch_variables():
    from webshaper.query import canonical
    from webshaper.models import Query
    import time
    branches = []
    for b in range(2):
        branches.append([{"subject": "?company", "predicate": "builds", "object": f"?p{b}_{i}"} for i in range(7)])
    query = Query(branches=branches)
    start = time.monotonic()
    value = canonical(query)
    assert value and time.monotonic() - start < 2
