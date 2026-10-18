"""Gold store. This module may be imported ONLY by the WideSearch grader."""
import json
import pandas as pd


def load_query_parts(download, task_id):
    rows = [json.loads(line) for line in (download / "widesearch.jsonl").read_text().splitlines()]
    row = next(r for r in rows if r["instance_id"] == task_id)
    evaluation = json.loads(row["evaluation"])
    answer = pd.read_csv(download / "widesearch_gold" / (task_id + ".csv"))
    answer.columns = [c.strip().lower().replace(" ", "") for c in answer.columns]
    return row, evaluation, answer[evaluation["required"]]
