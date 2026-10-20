from pathlib import Path
import tempfile, json, random, string, os
from types import SimpleNamespace
from loop_research.archive import RunContext, read_jsonl
from loop_research.config import Config
from loop_research.codex_backend import CodexBackend
from loop_research.refine import Refiner
from loop_research.harness import Harness
from loop_research.trace import Trace
marker='rejected-attempt-raw-content-7c6fe6083f0c4ade'
with tempfile.TemporaryDirectory(prefix='fetch-review-offline-') as td:
    root=Path(td); os.environ['TMPDIR']=td; tempfile.tempdir=td
    config=Config.load('config.yaml'); config.codex.log_full_text=False
    ctx=RunContext(root,'review',config,'fixture',trace=Trace(root/'runs/review'))
    seen=[]
    proposal={'summary':'No supported durable update.','edits':[],'additional_candidates':[],'decisions':[]}
    def runner(command, **kwargs):
        seen.append(kwargs['input'])
        out=Path(command[command.index('--output-last-message')+1])
        if len(seen)==1:
            out.write_text(marker)
            return SimpleNamespace(returncode=1,stdout='',stderr='temporary transport failure')
        out.write_text('```repl\nimport json\nanswer["content"] = json.dumps('+repr(proposal)+')\nanswer["ready"] = True\n```')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    backend=CodexBackend(ctx,runner=runner,sleep=lambda _:None,jitter=lambda:0)
    obs={'trajectory':[{'type':'tool','result':''.join(random.Random(13).choices(string.ascii_letters,k=1060000))}], 'self_check':{'ok':True,'issues':[],'signals':[]}}
    refiner=Refiner(Harness(root/'harness'),ctx,backend,lambda:obs)
    try:
        refiner.run(); refiner.boundary(wait=True)
    finally: refiner.close()
    matches=[str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and marker.encode() in p.read_bytes()]
    calls=read_jsonl(ctx.path/'codex_calls.jsonl')
    print(json.dumps({'attempts':len(seen),'state':ctx.load('refine_state.json')['status'],'raw_failed_response_chars':len(marker),'failed_backend_record':{k:calls[0].get(k) for k in ['attempt','exit_code','response_chars','response','prompt']},'archive_files_containing_failed_response':matches},indent=2))
