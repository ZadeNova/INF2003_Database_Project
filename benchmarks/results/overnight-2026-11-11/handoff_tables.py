import collections,csv,json,statistics
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];RESULTS=ROOT/'benchmarks/results'
def read(p):
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def write(name,rows):
 with (OUT/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
h=read(OUT/'sessions/headline.csv');b1=[];b4=[]
for r in h:
 if r['output'].startswith('B1'):
  peers=[x for x in h if x['output']==r['output'] and x['clients']==r['clients'] and x['headline']=='True' and x['variant']!='documents_hinted']
  fastest=min(float(x['p50_ms']) for x in peers)
  b1.append(dict(output=r['output'],engine=r['engine'],variant=r['variant'],clients=r['clients'],p50_ms=r['p50_ms'],session_min_ms=r['p50_session_min_ms'],session_max_ms=r['p50_session_max_ms'],ratio_to_fastest=float(r['p50_ms'])/fastest,headline=r['headline']))
 if r['output'].startswith('B4') and r['variant']=='after':
  before=next(x for x in h if x['output']==r['output'] and x['engine']==r['engine'] and x['variant']=='before')
  b4.append(dict(output=r['output'],engine=r['engine'],before_p50_ms=before['p50_ms'],after_p50_ms=r['p50_ms'],before_over_after=float(before['p50_ms'])/float(r['p50_ms']),before_session_min_ms=before['p50_session_min_ms'],before_session_max_ms=before['p50_session_max_ms'],after_session_min_ms=r['p50_session_min_ms'],after_session_max_ms=r['p50_session_max_ms'],headline=before['headline']=='True' and r['headline']=='True'))
write('b1-comparison.csv',b1);write('b4-comparison.csv',b4)
hardware=[]
for n in (1,2,3):
 p=next(RESULTS.glob(f'*_505222f4_overnight-session-{n}'));host=json.loads((p/'host.json').read_text())
 for c in host['containers']+[{'name':'runner','limits':host['runner_actual_limits']}]:
  hardware.append(dict(session=n,cpu_model=host['hardware']['cpu']['Name'].strip(),host_reported_ram_bytes=host['hardware']['ram'],vm_cpus=host['docker_vm']['NCPU'],vm_usable_ram_bytes=host['docker_vm']['MemTotal'],vm_meets_gate=host['vm_meets_plan'],container=c['name'],cpu_limit=c['limits']['NanoCpus']/1e9,memory_limit_bytes=c['limits']['Memory'],memory_plus_swap_limit_bytes=c['limits']['MemorySwap'],cpuset=c['limits']['CpusetCpus']))
write('hardware.csv',hardware)
stamp=next(RESULTS.glob('*_505222f4_redis-stampede'));s=read(stamp/'stampede.csv');summary=[]
for mode in sorted({r['mode'] for r in s}):
 rows=[r for r in s if r['mode']==mode]
 summary.append(dict(mode=mode,repetitions=len(rows),requests=sum(int(r['requests']) for r in rows),computed=sum(int(r['computed']) for r in rows),waited=sum(int(r['waited']) for r in rows),hit=sum(int(r['hit']) for r in rows),median_of_round_medians_ms=statistics.median(float(r['median_ms']) for r in rows),min_round_median_ms=min(float(r['median_ms']) for r in rows),max_round_median_ms=max(float(r['median_ms']) for r in rows)))
write('stampede-summary.csv',summary)
sp=json.loads((stamp/'provenance.json').read_text());assert sp['commit']=='505222f41b7473260ed9f40bb3bbaf8eafa46757' and not sp['pilot']
assert len(s)==sp['repetitions']*2 and all(int(r['requests'])==sp['simultaneous'] for r in s)
assert all(int(r['calls'])==sp['limiter_calls'] for r in read(stamp/'limiter.csv'))
# Keep the append-only command log untouched; accept escaped separators from orchestration handoff records.
text=(OUT/'execution.jsonl').read_text();decoder=json.JSONDecoder();commands=[]
while text.strip():
 text=text.lstrip()
 while text.startswith('\\n'):text=text[2:].lstrip()
 if not text:break
 value,end=decoder.raw_decode(text);commands.append(value);text=text[end:]
write('commands.csv',[dict(step=r['step'],exit_code=r['exit_code'],seconds=r.get('seconds',''),arguments=json.dumps(r.get('args',[]))) for r in commands])
(OUT/'supplement-verification.json').write_text(json.dumps({'stampede_provenance_verified':True,'limiter_calls_reached_redis':'existing script fails otherwise','raw_limiter_latencies':'not retained by existing tool; aggregates only','measurement_code_changed':False,'command_records':len(commands)},indent=2)+'\n')
print(json.dumps({'generated':['b1-comparison.csv','b4-comparison.csv','hardware.csv','stampede-summary.csv','commands.csv'],'stampede_verified':True}))
