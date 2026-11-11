import collections,csv,hashlib,json,math,re,subprocess,sys
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
sys.path.insert(0,str(Path.cwd()))
from benchmarks import request_timing as timing
from benchmarks.redis_stats import BURN_IN_LIMIT,BURN_IN_VIEWS,latin_square
ROOT=Path.cwd();OUT=ROOT/'benchmarks/results/collectors-2026-11-11';RESULTS=ROOT/'benchmarks/results';COMMIT='df03cb33c12deffceb6a1d298e7a2bbbc3e0a97e'
page=next(RESULTS.glob('*_df03cb33_request-timing'));failed=next(RESULTS.glob('*_df03cb33_redis'));prov=json.loads((page/'provenance.json').read_text());assert prov['commit']==COMMIT and prov['requests_per_page']==20 and prov['warmup_passes']==1 and prov['sequential']
with (page/'requests.csv').open(newline='') as f:rows=list(csv.DictReader(f))
assert len(rows)==100 and len({r['request_id'] for r in rows})==100
counts=collections.Counter(r['page'] for r in rows);assert set(counts)==set(prov['pages']) and all(n==20 for n in counts.values())
logs=subprocess.check_output(['docker','compose','-p',prov['project'],'logs','--no-color','--no-log-prefix','web'],text=True,encoding='utf-8')
parsed=timing.parse_request_logs(logs,{r['request_id'] for r in rows});assert len(parsed)==100
responses=[{'page':r['page'],'path':r['path'],'request_id':r['request_id'],'status':int(r['status'])} for r in rows]
joined=timing.join_requests(responses,parsed)
for old,new in zip(rows,joined,strict=True):
 for key in (*timing.METRICS,'db_share_percent'):assert math.isclose(float(old[key]),new[key],rel_tol=1e-12,abs_tol=1e-12),(key,old[key],new[key])
with (page/'joined-request-logs.jsonl').open('w') as f:
 for identity,value in sorted(parsed.items()):f.write(json.dumps(value,sort_keys=True)+'\n')
summary=[]
for name,path in prov['pages'].items():
 expected={'page':name,'path':path,**timing.aggregate([r for r in joined if r['page']==name])}
 with (page/(name+'.csv')).open(newline='') as f:actual=next(csv.DictReader(f))
 for key,value in expected.items():
  assert (math.isclose(float(actual[key]),value,rel_tol=1e-12,abs_tol=1e-12) if isinstance(value,(float,int)) else actual[key]==value),(name,key)
 summary.append(expected)
timing.write_csv(OUT/'page-summary.csv',summary)
source=ROOT/'data/derived/olist/clean';manifest=hashlib.sha256((source/'checksums.txt').read_bytes()).hexdigest();assert manifest==prov['source_manifest_sha256']
product=int(re.search(r'/products/(\d+)/',prov['pages']['product_detail'])[1]);spec=next(r for l in (source/'product_specs.ndjson').open(encoding='utf-8') if (r:=json.loads(l))['_id']==product);assert spec['attributes']
with (source/'categories.csv').open(newline='',encoding='utf-8') as f:category=next(r for r in csv.DictReader(f) if int(r['id'])==spec['category_id'])
assert prov['pages']['category']==f"/products/category/{category['slug']}/"
query=parse_qs(urlsplit(prov['pages']['faceted_search']).query);assert query['category']==[str(spec['category_id'])]
key,value=sorted(spec['attributes'].items())[0];assert query['attr_'+key]==[str(value).lower() if isinstance(value,bool) else str(value)]
diag_text=(OUT/'diagnostic-mongo.log').read_text(encoding='utf-8-sig');diagnosis=json.loads(next(l[5:] for l in diag_text.splitlines() if l.startswith('DIAG ')));assert diagnosis['control_product_id']==product and diagnosis['distinct_control_sessions']==1 and diagnosis['real_control_view_events']==BURN_IN_LIMIT*BURN_IN_VIEWS+1 and diagnosis['control_ranked_row']['views']==1 and diagnosis['leader']['views']>1
failure={'source_commit':COMMIT,'collector':'benchmarks.redis_experiment','exit_code':1,'phase':'untimed ranking burn-in','error':'The trending ranking did not settle during the burn-in','timed_samples':0,'accepted_timings':0,'requested_protocol':{'cheap_requests_per_page_condition_round':150,'dashboard_requests_per_condition_round':15,'rounds':4,'conditions':['off','cold','warm','down'],'seed':82,'order':latin_square(82)},'diagnosis':diagnosis,'source_fix':'PR #41 successfully selected source-backed product; this is a different burn-in defect','disposition':'excluded; no gate bypass or identical retry; reviewed burn-in fix required'}
(failed/'failure.json').write_text(json.dumps(failure,indent=2)+'\n');(OUT/'redis-failure-diagnosis.json').write_text(json.dumps(diagnosis,indent=2)+'\n')
old='505222f41b7473260ed9f40bb3bbaf8eafa46757';names=subprocess.check_output(['git','diff','--name-only',old,COMMIT],text=True).splitlines();assert not any(n.startswith(('src/','data/')) or n=='compose.yaml' for n in names)
(OUT/'source-revisions.json').write_text(json.dumps({'driver_and_stampede_commit':old,'collector_commit':COMMIT,'changed_files':names,'application_and_data_unchanged':True,'request_selection_fix':'PR #41; select first visible source-backed product with attributes'},indent=2)+'\n')
validation={'page_collector_passed':True,'response_log_joins_verified':len(joined),'requests_per_page':dict(counts),'aggregate_reproduction':'all values match existing aggregate()','selected_source_product':product,'paths_source_verified':True,'source_manifest_sha256':manifest,'redis_collector_passed':False,'redis_burn_in_failed':True,'redis_timed_samples':0,'overall_closeout_complete':False,'independent_evidence_review':'pending'}
(OUT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
commands=[json.loads(l) for l in (OUT/'commands.jsonl').read_text().splitlines()];timing.write_csv(OUT/'command-outcomes.csv',[{'step':r['step'],'exit_code':r['exit_code'],'duration_seconds':r['duration_seconds']} for r in commands]);print(json.dumps(validation))

