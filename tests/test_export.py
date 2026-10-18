from test_validation import candidate

import json
import pytest


@pytest.mark.parametrize("retrospective", [False, True])
@pytest.mark.parametrize("redistributable", [False, True])
def test_public_corpus_matches_temporal_access_and_keeps_private_snapshots(tmp_path, retrospective, redistributable):
    from webshaper.fixtures import fixture_config
    from webshaper.models import SourceInput
    from webshaper.pipeline import run
    from webshaper.sources import SourceStore
    from webshaper.validation import documents_for
    config = fixture_config()
    config.scope.allow_retrospective = retrospective
    for name, published in [("future", "2026-01-01"), ("undated", None)]:
        path = tmp_path / (name + ".txt")
        path.write_text("FICTIONAL EXTRA SOURCE: " + name)
        config.sources.append(SourceInput(origin=str(path), title=name, published_at=published,
                              date_basis="fixture", category="fixture", redistributable=redistributable))
    root = tmp_path / "run"
    assert run(config, root)["accepted_tasks"] == 1
    entries = [json.loads(line) for line in (root / "export/public/corpus.jsonl").read_text().splitlines()]
    origins = {entry["url"] for entry in entries}
    expected = {s.origin for s in config.sources[:2]}
    if retrospective:
        expected.add(str(tmp_path / "future.txt"))
    assert origins == expected  # Exclude entire metadata entries, even when text is withheld.
    store = SourceStore(root / "sources")
    sources = store.all()
    assert {d["url"] for d in documents_for(sources, store, config.as_of, retrospective)} == expected
    assert len(sources) == 4
    assert len((root / "export/sources.jsonl").read_text().splitlines()) == 4
    for source in sources:
        assert store.read(source)  # Private raw/text snapshots remain intact and hash-valid.


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
