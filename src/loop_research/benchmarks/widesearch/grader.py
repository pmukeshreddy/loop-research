"""Load unchanged pinned scoring source; replace only its provider transport."""
import builtins
import ast
from contextlib import redirect_stdout
from contextvars import ContextVar
from dataclasses import asdict
from io import StringIO
import json
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
import pandas as pd
from loguru import logger
from . import answers
from .data import WideSearchData, DATASET_REVISION, CODE_REVISION
from .. import GradeResult
from ...archive import digest, read_json, write_json
from ...codex_backend import CodexBackend

_BACKEND = ContextVar("widesearch_backend")
_MODULE_LOCK = threading.Lock()
_MODULES = {}


def official_modules(code):
    code = Path(code).resolve()
    with _MODULE_LOCK:
        if code in _MODULES:
            return _MODULES[code]
        private = {}
        bridge = ModuleType("loop_official_widesearch_llm")
        def llm_completion(*, messages, model_config_name):
            backend = _BACKEND.get()
            prompt = messages if isinstance(messages, str) else json.dumps(messages, ensure_ascii=False)
            key = digest({"prompt": prompt, "code": CODE_REVISION, "config": backend.ctx.config.model_dump()})
            path = backend.ctx.path / "judge_cache" / (key + ".json")
            cached = read_json(path)
            response = cached["content"] if cached is not None else backend.complete(
                prompt, purpose="grade", model=backend.ctx.config.models.judge)
            # The official parser expects fenced JSON; fail a malformed judge rather than silently awarding zeros.
            parsed = private["src.evaluation.metric_utils"].parse_markdown_json(response)
            if not isinstance(parsed, dict):
                raise ValueError("Official judge response did not contain a fenced JSON object")
            metric = private["src.evaluation.metric_utils"]
            if prompt.startswith(metric.eval_column_prompt.split("\n", 1)[0]):
                items = ast.literal_eval(prompt.split("====== response-start ======\n", 1)[1]
                                         .rsplit("\n====== response-end ======", 1)[0])
                if set(parsed) != set(items) or any(type(score) is not int or score not in (0, 1)
                                                   for score in parsed.values()):
                    raise ValueError("Official judge must return one binary integer score for every requested item")
            elif any(not isinstance(value, str) for value in parsed.values()):
                raise ValueError("Official judge alignment must map strings to strings")
            if cached is None:
                write_json(path, {"content": response})
            return SimpleNamespace(content=response)
        bridge.llm_completion = llm_completion
        private["src.utils.llm"] = bridge
        original_import = builtins.__import__
        def redirected(name, globals=None, locals=None, fromlist=(), level=0):
            if name in private:
                return private[name]
            if name.startswith("src."):
                raise ImportError(f"Unverified upstream import: {name}")
            return original_import(name, globals, locals, fromlist, level)
        for name in ("src.utils.utils", "src.evaluation.data_loader", "src.evaluation.metric_utils", "src.evaluation.evaluation"):
            path = code / (name.replace(".", "/") + ".py")
            alias = "loop_official_widesearch_" + name.replace(".", "_")
            mod = ModuleType(alias)
            mod.__file__ = str(path)
            mod.__builtins__ = dict(vars(builtins), __import__=redirected)
            sys.modules[alias] = mod
            private[name] = mod
            logger.disable(alias)
            # Upstream initializes pandarallel with verbose output at import time.
            with redirect_stdout(StringIO()):
                exec(compile(path.read_bytes(), str(path), "exec"), mod.__dict__)
        _MODULES[code] = private
        return private


def error_breakdown(detail, evaluation):
    result = {"missing_entities": [], "wrong_additions": [], "partial_rows": []}
    for record in detail.to_dict(orient="records"):
        entity = {key: str(record.get(key, "")) for key in evaluation["unique_columns"]}
        if record.get("exist_flag_gt") == 1 and pd.isna(record.get("exist_flag_response")):
            result["missing_entities"].append(entity)
        elif record.get("exist_flag_response") == 1 and pd.isna(record.get("exist_flag_gt")):
            result["wrong_additions"].append(entity)
        else:
            columns = [col for col in evaluation["required"] if any(
                record.get(f"{col}_{metric}", 1) < 1 for metric in evaluation["eval_pipeline"][col].get("metric", []))]
            if columns:
                result["partial_rows"].append({"entity": entity, "columns": columns})
    return result


class WideSearchBenchmark(WideSearchData):
    def grade(self, task, submission, run_ctx, *, backend=None):
        self.verify_code()
        modules = official_modules(self.code)
        loader, evaluator = modules["src.evaluation.data_loader"], modules["src.evaluation.evaluation"]
        row, evaluation, answer = answers.load_query_parts(self.download, task.task_id)
        query = loader.WideSearchQuery(task.task_id, row["query"], evaluation, answer, row["language"])
        response = loader.WideSearchResponse(**submission) if submission is not None else None
        run_ctx.path.mkdir(parents=True, exist_ok=True)
        path = run_ctx.path / "alignment.csv"
        token = _BACKEND.set(backend or CodexBackend(run_ctx))
        try:
            result = evaluator.evaluate_single_query(query, response, str(path))
        finally:
            _BACKEND.reset(token)
        if result.msg.startswith("evaluator error:"):
            raise RuntimeError(result.msg)
        if submission is None:
            errors = {"missing_entities": answer[evaluation["unique_columns"]].astype(str).to_dict(orient="records"),
                      "wrong_additions": [], "partial_rows": []}
        elif path.exists():
            errors = error_breakdown(pd.read_csv(path), evaluation)
        else:
            errors = {"format_error": result.msg}
        raw = asdict(result)
        return GradeResult(metrics={k: float(v) for k, v in raw.items() if k not in ("instance_id", "msg")},
            primary_metric="f1_by_row", errors=errors, judge=run_ctx.config.judge_label,
            provenance={"dataset_revision": DATASET_REVISION, "code_revision": CODE_REVISION,
                        "official_message": result.msg, "alignment": str(path) if path.exists() else None})
