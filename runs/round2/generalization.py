"""Report the exact archived-task generalization replay without changing evidence."""
from pathlib import Path
import hashlib, json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def read(p):return json.loads(p.read_text())
def link(label,p):return f'[{label}]({p})'
def table(headers,rows):
 return ['| '+' | '.join(map(str,headers))+' |','| '+' | '.join('---' for _ in headers)+' |', *['| '+' | '.join(map(str,r))+' |' for r in rows],'']
b=read(HERE/'SI.baseline.json'); old=read(HERE/'SI_baseline/SI.metrics_partial.json')
a=read(HERE/'SI.audit.json');m=read(HERE/'SI.metrics.json');task=Path(a['task_path']);newtask=read(task/'task.json')
assert newtask==b['task']
assert m['manifest']['base_sha']==b['harness']['initial_sha']
cur=read(task/'output.json')
def values(data):
 return {r['cells']['quantity']['value'].casefold(): {k:str(v['value']).casefold() for k,v in r['cells'].items()} for r in data['rows']}
same=values(cur)==values(b['output'])
issues=len(m['issues']);uncited=m['uncited_cells']; quality= same and len(cur['rows'])==b['quality']['row_count'] and issues==0 and uncited==0
root=[r for r in a['rlms'] if r['depth']==0]
rows=[['Codex attempts',old['codex_calls'],m['codex_calls']],['Wall seconds',old['wall_s'],m['wall_s']],['Root iterations',old['root_iterations'],sum(r['iterations'] for r in root)],['Root termination','answer ready (submission archived)',','.join(r['termination'] for r in root)],['Returned fetched characters',old['page_chars'],a['overlap']['total_chars']],['Raw opened-page characters','unavailable','unavailable' if not any(f.get('raw_page_chars') is not None for f in a['fetches']) else 'see fetch inventory'],['Largest root input',old['max_root_prompt_chars'],a['largest_prompt']['total']],['50-character overlap fraction',old['overlap_covered_chars']/old['overlap_total_chars'],a['overlap']['fraction']],['Sub-calls',old['calls_by_purpose']['sub'],a['subcall_count']],['Sub-call input characters',old['subcall_input_chars'],a['subcall_input_chars']],['Children',0,len([r for r in a['rlms'] if r['depth']>0])],['Refine planner calls',old['calls_by_purpose']['refine'],m['calls_by_purpose'].get('refine',0)],['Failed fetches',old['failed_fetches'],m['failed_fetches']],['Rows',old['rows'],m['rows']],['Uncited cells',len(old['uncited']),uncited],['Archived self-check issues',len(old['issues']),issues],['Signals','field did not exist',len(m['signals'])]]
lines=['## SI generalization check','',f'Quality preservation: **{"works" if quality else "does not pass"}**. Exact same five-quantity question, schema, language and starting harness as the earlier verified run. All quantity/unit/symbol values match: **{same}**. Current issues: **{issues}**; uncited cells: **{uncited}**; rows: **{m["rows"]}**.','',link('Exact earlier task and provenance',HERE/'SI.baseline.md')+'; '+link('Current task',task/'task.json')+'; '+link('Current cited output',task/'output.json')+'.','', 'This is separate from the explicit child/refinement mechanism check. The earlier run had three stalled-search issues and an archived false self-check; that historical result is unchanged. Those event types belong to signals under the current split. Current code and depth 2 are the same as the four new proof arms; the earlier depth was 1. The same effective date is retained using the explicit date policy.','']
lines+=table(['Measurement','Earlier SI run','Round 2 SI'],rows)
lines+=['Largest-root disjoint parts:', '']+table(['Part','Earlier characters','Current characters'],[[k,old['largest_prompt_parts'][k],v] for k,v in a['largest_prompt']['parts'].items()])
lines+=['All current loops, subcalls, page-variable excerpts, per-fetch sizes, issues/signals, full planner decisions, commits and their timestamps appear in the SI sections of this report. Legacy missing fields are documented in '+link('partial baseline audit',HERE/'SI_baseline/SI.audit_partial.json')+' rather than fabricated.','', 'One pair is mechanism evidence, not a statistical result. Observed call and time differences are reported without claiming a reproducible performance change.','']
(HERE/'SI.generalization.md').write_text('\n'.join(lines)+'\n')
provenance={'run_id':a['run_id'],'task_id':task.name,'task_path':str(task),'base_sha':m['manifest']['base_sha'],
            'task_sha256':hashlib.sha256((task/'task.json').read_bytes()).hexdigest(),
            'output_sha256':hashlib.sha256((task/'output.json').read_bytes()).hexdigest(),
            'baseline_path':str(HERE/'SI.baseline.json'),
            'baseline_sha256':hashlib.sha256((HERE/'SI.baseline.json').read_bytes()).hexdigest(),
            'prior_run_id':b['identity']['run_id']}
(HERE/'SI.generalization.json').write_text(json.dumps({'same_exact_task':True,'same_values':same,'quality_preserved':quality,'issues':issues,'uncited':uncited,'rows':m['rows'],'measurements':rows,'provenance':provenance},indent=2)+'\n')
print(json.dumps({'same_values':same,'quality_preserved':quality,'issues':issues,'uncited':uncited}))
