from pathlib import Path
import tempfile,json,os,hashlib,copy
from types import SimpleNamespace
from loop_research.archive import RunContext,read_jsonl
from loop_research.config import Config
from loop_research.codex_backend import CodexBackend
from loop_research.harness import Harness
from loop_research.refine import Refiner
main=Path('/Users/mukeshreddypochamreddy/Desktop/loop-research')
p=main/'runs/round3/cohorts/quoted_text_v1/workspaces/A/runs/research-f43c96b33c5d43b299e491341eb65216/289901ce021c28d56fdac993/refine_state.json'
before=p.read_bytes();original=json.loads(before)
logical_sha=original['planner_representation']['logical_payload_sha256']
schema_sha=hashlib.sha256(json.dumps(original['planner_schema']).encode()).hexdigest()
with tempfile.TemporaryDirectory(prefix='fetch-review-saved-') as td:
    root=Path(td);os.environ['TMPDIR']=td;tempfile.tempdir=td
    ctx=RunContext(root,'review',Config.load('config.yaml'),'fixture')
    calls=[]
    code=f'''import json,hashlib
assert hashlib.sha256(json.dumps(context,ensure_ascii=False).encode()).hexdigest()=={logical_sha!r}
assert hashlib.sha256(json.dumps(proposal_schema).encode()).hexdigest()=={schema_sha!r}
assert context==snapshot()
proposal={{'summary':'Offline transport fixture only; no semantic evaluation.','edits':[],'additional_candidates':[],'decisions':[{{'candidate_id':c['id'],'decision':'declined','reason':'Offline transport fixture preserves full accounting.','evidence_refs':c['evidence_refs'],'edit_indexes':[]}} for c in context['candidate_inventory']]}}
from jsonschema import Draft202012Validator
Draft202012Validator(proposal_schema).validate(proposal)
answer['content']=json.dumps(proposal)
answer['ready']=True'''
    def runner(command,**kwargs):
        calls.append(kwargs['input']);assert len(kwargs['input'])<=1048576
        Path(command[command.index('--output-last-message')+1]).write_text('```repl\n'+code+'\n```')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    refiner=Refiner(Harness(root/'harness'),ctx,CodexBackend(ctx,runner=runner),lambda:original['observed'])
    job=copy.deepcopy(original);job.update(job_id='offline-exact-snapshot',status='planning',proposal=None)
    try: planned=refiner._plan_job(job)
    finally:refiner.close()
    assert planned['status']=='planned'
    directory=ctx.path/'refine_planners/offline-exact-snapshot'
    exact=(directory/'context.json').read_bytes();schema=json.loads((directory/'schema.json').read_text())
    assert hashlib.sha256(exact).hexdigest()==logical_sha
    assert schema==original['planner_schema'];assert p.read_bytes()==before
    print(json.dumps({'status':'planned_offline_mock_only','logical_chars':len(exact.decode()),'logical_sha256':hashlib.sha256(exact).hexdigest(),'strict_schema_sha256':schema_sha,'strict_schema_unchanged':True,'original_file_unchanged':True,'prospective_legacy_backend_chars':len(planned['planner_prompt'])+182,'actual_fake_dispatch_chars':[len(x) for x in calls],'call_purposes':[x['purpose'] for x in read_jsonl(ctx.path/'codex_calls.jsonl')],'complete_candidate_decisions':len(planned['proposal']['decisions'])},indent=2))
