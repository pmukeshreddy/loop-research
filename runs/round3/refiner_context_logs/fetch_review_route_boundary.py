from pathlib import Path
import tempfile, json
from loop_research.archive import RunContext
from loop_research.config import Config
from loop_research.codex_backend import INSTRUCTION
from loop_research.harness import Harness
from loop_research.refine import Refiner
from loop_research import refine_context
proposal=json.dumps({'summary':'No supported durable update.','edits':[],'additional_candidates':[],'decisions':[]})
class Fake:
    def __init__(self): self.prompts=[]
    def complete(self,prompt,**kwargs): self.prompts.append(prompt); return proposal
with tempfile.TemporaryDirectory(prefix='fetch-review-boundary-') as td:
    root=Path(td); config=Config.load('config.yaml'); harness=Harness(root/'harness'); results=[]
    def one(n, limit):
        ctx=RunContext(root,'review',config,str(n)); backend=Fake(); planner=[]
        refine_context.MAX_PROMPT_CHARS=limit
        refine_context.plan_context=lambda *args: (planner.append(args),proposal)[1]
        refiner=Refiner(harness,ctx,backend,lambda:{'trajectory':[],'self_check':{'ok':True}})
        try:
            refiner.run(); refiner.boundary(wait=True)
        finally: refiner.close()
        job=ctx.load('refine_state.json'); size=len(INSTRUCTION+job['planner_prompt'])
        return {'limit':limit,'backend_prompt_chars':size,'direct_calls':len(backend.prompts),'context_calls':len(planner),'status':job['status']}
    observed=one('probe',10**9)['backend_prompt_chars']
    for name,delta in [('one_below_limit',1),('exact_limit',0),('one_above_limit',-1)]:
        row=one(name,observed+delta);row['case']=name;results.append(row)
        assert row['context_calls']==(delta<0)
        assert row['direct_calls']==(delta>=0)
    print(json.dumps(results,indent=2))
