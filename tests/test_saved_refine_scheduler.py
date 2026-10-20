"""Real replay case admission; offline case bodies expose entry and release events."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import threading

from test_saved_refine_input import helper


def prepared_replay(module, tmp_path, monkeypatch, count, limit):
    cases = [{"label": str(index), "root": str(tmp_path / str(index)),
              "config": {"codex": {"max_concurrent": limit, "timeout_s": 600},
                         "refine": {"max_edits": 2}},
              "saved_payload": {"observations": ["complete fixture"], "candidate_inventory": []}}
             for index in range(count)]
    module.save(tmp_path / "prepared.json", {
        "status": "prepared", "script": module.file_record(Path(module.__file__).resolve()),
        "source_root": str(tmp_path), "cases": cases,
    })
    # Source/install/harness verification is orthogonal to this offline scheduler
    # fixture. The actual execute() coordinator and executor remain unchanged.
    monkeypatch.setattr(module, "verify_installed_source", lambda *_: {"commit": "offline-source"})
    monkeypatch.setattr(module, "verify_originals", lambda _: None)
    return cases


def test_fifth_case_does_not_start_its_budget_until_one_of_four_active_cases_finishes(tmp_path, monkeypatch):
    module = helper()
    cases = prepared_replay(module, tmp_path, monkeypatch, count=5, limit=4)
    before = copy.deepcopy(cases)
    entered = [threading.Event() for _ in cases]
    release = [threading.Event() for _ in cases]
    first_four = threading.Event()
    lock = threading.Lock()
    events = []
    active = peak = 0

    def offline_case(case, cancellation):
        nonlocal active, peak
        index = int(case["label"])
        with lock:
            active += 1
            peak = max(peak, active)
            events.append(("start", index))
            entered[index].set()
            if all(event.is_set() for event in entered[:4]):
                first_four.set()
        assert release[index].wait(10), "Test did not release its offline case"
        with lock:
            events.append(("end", index))
            active -= 1
        return {"label": case["label"], "status": "complete", "case_input": case}

    monkeypatch.setattr(module, "replay_case", offline_case)
    with ThreadPoolExecutor(max_workers=1) as driver:
        execution = driver.submit(module.execute, tmp_path, "offline-source")
        try:
            assert first_four.wait(5), "Four independent cases should run concurrently"
            assert not entered[4].wait(0.2), "Fifth case started while all four case slots were occupied"
            release[0].set()
            assert entered[4].wait(5), "Queued fifth case did not start after an active case completed"
        finally:
            for event in release:
                event.set()
            result = execution.result(timeout=10)
    assert peak == 4
    assert events.index(("end", 0)) < events.index(("start", 4))
    assert result["status"] == "complete" and len(result["results"]) == 5
    assert result["max_concurrent_cases"] == 4
    assert {row["label"]: row["case_input"] for row in result["results"]} == {
        row["label"]: row for row in before}
    assert json.loads((tmp_path / "prepared.json").read_text())["cases"] == before


def test_fewer_cases_keep_available_parallelism_and_failures_are_retained(tmp_path, monkeypatch):
    module = helper()
    prepared_replay(module, tmp_path, monkeypatch, count=2, limit=4)
    both_entered = threading.Barrier(2)

    def offline_case(case, cancellation):
        both_entered.wait(timeout=5)
        if case["label"] == "0":
            raise RuntimeError("Deliberate offline case failure")
        return {"label": case["label"], "status": "complete"}

    monkeypatch.setattr(module, "replay_case", offline_case)
    result = module.execute(tmp_path, "offline-source")
    assert result["max_concurrent_cases"] == 2
    assert result["status"] == "failed" and len(result["results"]) == 2
    failed = next(row for row in result["results"] if row["label"] == "0")
    assert failed["error"] == "RuntimeError: Deliberate offline case failure"
    assert "traceback" in failed
