import csv,hashlib,json,subprocess,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from benchmarks.redis_report import read_samples
from benchmarks.report import table
ROOT=Path.cwd();R=ROOT/'benchmarks/results';OUT=R/'redis-final-2026-11-11';new=next(R.glob('*_eb9b39eb_redis'));p=json.loads((new/'provenance.json').read_text());rows=[]
sessions=[next(R.glob('*_505222f4_overnight-session-'+str(n))).name for n in (1,2,3)]
for workload in ('B1','B2','B3','B4','B5','B6'):
 rows.append({'group':workload,'commit':'505222f41b7473260ed9f40bb3bbaf8eafa46757','directories':';'.join(sessions),'primary_table':'overnight-2026-11-11/sessions/b2-headline.csv' if workload=='B2' else 'overnight-2026-11-11/sessions/headline.csv','raw_evidence':';'.join(d+'/raw.jsonl.gz' for d in sessions),'status':'valid; use every session and predeclared headline flags'})
page=next(R.glob('*_df03cb33_request-timing'));stamp=next(R.glob('*_505222f4_redis-stampede'))
for name,commit,folder,primary,raw,status in [('application page timing','df03cb33c12deffceb6a1d298e7a2bbbc3e0a97e',page,'collectors-2026-11-11/page-summary.csv',page.name+'/requests.csv','valid; complete sequential page collector'),('Redis conditions',p['commit'],new,new.name+'/ratios.csv',new.name+'/samples.csv','partial accepted evidence; warm dashboard unavailable; consult comparison-usability.csv'),('Redis stampede','505222f41b7473260ed9f40bb3bbaf8eafa46757',stamp,'overnight-2026-11-11/stampede-summary.csv',stamp.name+'/stampede.csv','valid standalone experiment; aggregates retained'),('Redis limiter','505222f41b7473260ed9f40bb3bbaf8eafa46757',stamp,stamp.name+'/limiter.csv',stamp.name+'/limiter.csv','valid aggregate measurements; per-call raw latencies not retained by existing tool')]:rows.append({'group':name,'commit':commit,'directories':folder.name,'primary_table':primary,'raw_evidence':raw,'status':status})
table(OUT/'authoritative-evidence.csv',rows)
s=read_samples(new);drift=[]
for round_index in range(1,5):
 for page_name in ('shop','search','dashboard'):
  off=Counter(r['digest'] for r in s if r['round']==round_index and r['page']==page_name and r['condition']=='off');reference=off.most_common(1)[0][0]
  for condition in p['latin_square'][round_index-1]:
   blocks=[]
   for sample in (r for r in s if r['round']==round_index and r['page']==page_name and r['condition']==condition):
    if blocks and blocks[-1]['digest']==sample['digest']:blocks[-1]['samples']+=1
    else:blocks.append({'digest':sample['digest'],'samples':1,'matches_off_reference':sample['digest']==reference})
   drift.append({'round':round_index,'page':page_name,'condition':condition,'digest_blocks':blocks})
(OUT/'digest-blocks.json').write_text(json.dumps({'observations':drift,'limitation':'Bodies and changed link identities were not retained by the collector. Round-2 shop/search digests drifted during down and stayed changed for warm; the exact changed business-data links cannot be reconstructed. Do not waive those rejections.'},indent=2)+'\n')
changes=subprocess.check_output(['git','diff','--name-only','505222f41b7473260ed9f40bb3bbaf8eafa46757',p['commit']],text=True).splitlines();assert not any(n.startswith(('src/','data/')) or n=='compose.yaml' for n in changes)
(OUT/'revision-map.json').write_text(json.dumps({'groups':rows,'changes_from_driver_commit':changes,'application_data_compose_unchanged':True,'reason_for_revisions':'Reviewed collector source-selection and distinct-visitor repairs only; historical groups are never relabelled','overall_closeout_complete':False},indent=2)+'\n')
containers=json.loads((OUT/'containers-before.json').read_text());table(OUT/'configuration.csv',[{'container':r['name'],'image':r['image_tag'],'image_id':r['image_id'],'cpu_limit':r['limits']['NanoCpus']/1e9,'memory_limit_bytes':r['limits']['Memory'],'memory_plus_swap_limit_bytes':r['limits']['MemorySwap'],'cpuset':r['limits']['CpusetCpus'],'vm_cpus':p['host']['docker_vm']['NCPU'],'vm_memory_bytes':p['host']['docker_vm']['MemTotal']} for r in containers])
print(json.dumps({'authoritative_groups':len(rows),'old_artifacts':'unchanged','Redis_comparison_status':'partial; dashboard warm missing'}))
