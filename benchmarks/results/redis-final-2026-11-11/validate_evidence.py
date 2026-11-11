import collections,csv,hashlib,json,math,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from benchmarks.redis_report import read_samples,write_reports
from benchmarks.redis_stats import apply_gates,analyse,latin_square,CACHED_PAGES,CONTROL_PAGES
from benchmarks.report import table
ROOT=Path.cwd();OUT=ROOT/'benchmarks/results/redis-final-2026-11-11';result=next((ROOT/'benchmarks/results').glob('*_eb9b39eb_redis'));p=json.loads((result/'provenance.json').read_text());s=read_samples(result);commands=[json.loads(l) for l in (OUT/'commands.jsonl').read_text().splitlines()]
assert p['commit']=='eb9b39ebd296ed309dffc4ecf91a4b4a8cf08a78' and not p['pilot'] and p['seed']==82 and p['requests_dashboard']==15 and p['requests_per_cheap_page']==150
assert 2<=p['burn_in_passes']<=50 and p['burn_in_visitors']=='a fresh anonymous cookie jar per untimed control-product view'
assert p['latin_square']==latin_square(82) and len(s)==9840 and len({r['request_id'] for r in s})==9840
counts=collections.Counter((r['round'],r['condition'],r['page']) for r in s)
assert len(counts)==4*4*5 and all(n==(15 if key[2]=='dashboard' else 150) for key,n in counts.items())
for round_index,order in enumerate(p['latin_square'],1):
 seen=[]
 for r in s:
  if r['round']==round_index and (not seen or seen[-1]!=r['condition']):seen.append(r['condition'])
 assert seen==order
assert all(r['status']==200 and all(math.isfinite(r[k]) and r[k]>=0 for k in ('client_ms','duration_ms','db_pg_ms','db_mongo_ms','redis_ms')) for r in s)
accepted,refused=apply_gates(s);analysis=analyse(s);assert analysis['accepted']==9242 and analysis['refused']==598
assert next(r['exit_code'] for r in commands if r['step']=='redis-measurement')==0
with (result/'rounds.csv').open() as f:rounds=list(csv.DictReader(f))
assert [r['order'] for r in rounds]==[' '.join(order) for order in p['latin_square']]
cellcounts=collections.Counter((r['round'],r['condition'],r['page']) for r in accepted)
coverage=[{'round':key[0],'condition':key[1],'page':key[2],'requested':count,'accepted':cellcounts[key],'refused':count-cellcounts[key]} for key,count in sorted(counts.items())];table(OUT/'condition-coverage.csv',coverage)
reasons=collections.Counter((r['round'],r['condition'],r['page'],r['refusal']) for r in refused);table(OUT/'refusals-by-round.csv',[{'round':key[0],'condition':key[1],'page':key[2],'reason':key[3],'samples':n} for key,n in sorted(reasons.items())])
pairs=[]
for page in (*CACHED_PAGES,*CONTROL_PAGES):
 for top,bottom in [('off','warm'),('cold','off'),('down','off')]:
  valid=[n for n in range(1,5) if cellcounts[n,top,page] and cellcounts[n,bottom,page]]
  row=next((r for r in analysis['ratios'] if r['page']==page and r['pair']==top+'/'+bottom),None)
  pairs.append({'page':page,'pair':top+'/'+bottom,'usable_rounds':';'.join(map(str,valid)),'usable_round_count':len(valid),'complete_four_round_comparison':len(valid)==4,'ratio_median':row['ratio_median'] if row else '', 'status':'complete' if len(valid)==4 else 'accepted subset only' if valid else 'unavailable; all warm samples rejected'})
table(OUT/'comparison-usability.csv',pairs)
reports=['summary.csv','ratios.csv','bootstrap.csv','refusals.csv','verdicts.csv','chart.svg','analysis.json'];scratch=OUT/'regeneration.local';shutil.copytree(result,scratch,dirs_exist_ok=True);write_reports(scratch);assert all((scratch/name).read_bytes()==(result/name).read_bytes() for name in reports)
before=json.loads((OUT/'containers-before.json').read_text());after=json.loads((OUT/'containers-after.json').read_text());assert all(not r['state']['oom'] and not r['state']['paused'] and r['state']['restarts']==0 for r in after)
validation={'command_exit_zero':True,'source_commit':p['commit'],'pilot':False,'burn_in_passes':p['burn_in_passes'],'burn_in_leadership_and_stability':'required by settle() before entering rounds; unchanged gates passed','full_requested_matrix':True,'raw_samples':len(s),'unique_request_ids':len(s),'accepted':len(accepted),'refused':len(refused),'reports_regenerate_byte_identically':True,'warm_dashboard_accepted':sum(r['page']=='dashboard' and r['condition']=='warm' for r in accepted),'all_required_comparisons_available':all(r['usable_round_count']==4 for r in pairs),'overall_closeout_complete':False,'independent_review':'pending'}
(OUT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');table(OUT/'command-outcomes.csv',[{'step':r['step'],'exit_code':r['exit_code'],'duration_seconds':r['duration_seconds']} for r in commands]);print(json.dumps(validation));print(json.dumps([r for r in pairs if r['usable_round_count']<4]))
