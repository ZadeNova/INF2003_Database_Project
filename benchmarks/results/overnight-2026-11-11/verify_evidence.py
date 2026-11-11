"""Verify retained measurement artifacts and generate numerical handoff tables; no database access."""
import collections,csv,gzip,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
RESULTS=ROOT/'benchmarks/results'
COMMIT='505222f41b7473260ed9f40bb3bbaf8eafa46757'
def read(path):
 with Path(path).open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def write(name,rows):
 if not rows:return
 with (OUT/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def find(label):
 ps=list(RESULTS.glob('*_505222f4_'+label));assert len(ps)==1,(label,len(ps));return ps[0]
correct=find('overnight-correctness')
correct_host=json.loads((correct/'host.json').read_text());correct_rows=read(correct/'runs.csv')
assert correct_host['exit_code']==0 and correct_host['commit']==COMMIT and all(r['status']=='passed' for r in correct_rows)
expected=set()
for r in correct_rows:
 if r['phase']!='correctness':continue
 if r['output']=='B3':clients=[int(r['clients'])]
 elif r['output'].startswith('B4') or r['output']=='B2refresh':clients=[1]
 elif r['output'].startswith('B2'):clients=[1,10]
 else:clients=[1,10,50]
 for client in clients:expected.add((r['output'],r['engine'],r['variant'],str(client)))
checks=[];coverage=[];index=[];fingerprints=[]
for n in (1,2,3):
 p=find(f'overnight-session-{n}');h=json.loads((p/'host.json').read_text());v=json.loads((p/'provenance.json').read_text());rows=read(p/'runs.csv')
 assert h['exit_code']==0 and h['commit']==COMMIT and not h['container_events'] and h['final'] and h['vm_meets_plan']
 assert not any(r['status']!='passed' for r in rows)
 assert v['workload_matrix']['default']['operations_per_client']==50 and v['workload_matrix']['B2']['operations_per_client']==10
 assert v['fixed_b3_buyers']==50 and v['measured_runs']==5 and v['restores_since_load']==0
 assert v['settings']['postgres']['shared_buffers']=='512MB'
 assert h['mongo_server_readback']['cache_bytes']==805306368
 engines={c['name'].split('bench-')[-1]:c['limits'] for c in h['containers']}
 for c in h['containers']:assert c['limits']['NanoCpus']==4000000000 and c['limits']['Memory']==3221225472 and c['limits']['MemorySwap']==3221225472
 fingerprint=json.dumps({k:v[k] for k in ('files','manifest_sha256','golden_checksums','output_schema_sha256','libraries','settings')},sort_keys=True)
 fingerprints.append(fingerprint)
 counts=collections.Counter((r['output'],r['engine'],r['variant'],r['clients']) for r in rows if r['phase']=='measured')
 assert counts and all(count==5 for count in counts.values()),[x for x in counts.items() if x[1]!=5]
 assert set(counts)==expected,{'missing':list(expected-set(counts)),'extra':list(set(counts)-expected)}
 for prefix in ('baseline','baseline_roundtrip','baseline_end','baseline_roundtrip_end'):
  assert any(k[0]==prefix for k in counts),prefix
 groups=collections.defaultdict(list)
 for r in rows:groups[(r['output'],r['engine'],r['variant'],r['clients'])].append(r)
 for key,rs in groups.items():coverage.append(dict(session=n,output=key[0],engine=key[1],variant=key[2],clients=key[3],records=len(rs),measured_runs=sum(r['phase']=='measured' for r in rs),failed=sum(r['status']=='failed' for r in rs),accepted=sum(r['accepted']=='True' for r in rs)))
 raw=p/'raw.jsonl';compressed=p/'raw.jsonl.gz';digest=hashlib.sha256();operations=0;accepted=0;failed=0
 opener=gzip.open if compressed.exists() else open
 with opener(compressed if compressed.exists() else raw,'rb') as f:
  for line in f:
   digest.update(line);r=json.loads(line)
   if r.get('kind')=='operation':
    operations+=1;accepted+=bool(r.get('accepted'));failed+=r.get('status')=='failed'
    assert not(r.get('status')=='failed' and (r.get('accepted') or r.get('accepted_latency_ns') is not None))
 assert digest.hexdigest()==v['raw_sha256']
 required=['checks.csv','ratios.csv','pooled.csv','drift.csv','memory.csv','memory-settings.csv','b2-headline.csv','B3-states.csv','B6-states.csv','matrix-evidence.csv']
 for file in required:assert (p/'report'/file).is_file(),file
 assert list((p/'report').glob('*.svg')) and list((p/'plans').glob('*.json'))
 drift=sum(r['drift']!='no' for r in read(p/'report/drift.csv'))
 checks.append(dict(session=n,directory=p.name,commit=h['commit'],exit_code=h['exit_code'],failed_checks=0,container_events=len(h['container_events']),baseline_drift_flags=drift,raw_sha256_verified=True,raw_operations=operations,accepted_operations=accepted,raw_failed_operations=failed,report_files=len(list((p/'report').iterdir())),query_plan_files=len(list((p/'plans').glob('*.json'))),duration_seconds=h['duration_seconds']))
assert len(set(fingerprints))==1,'source, golden, driver or durability settings differ across sessions'
assert len({tuple((r['output'],r['engine'],r['variant'],r['clients']) for r in read(find(f'overnight-session-{n}')/'summary.csv')) for n in (1,2,3)})==1
write('validation.csv',checks);write('coverage.csv',coverage)
for p in sorted(RESULTS.glob('*_505222f4_*')):
 if not (p/'host.json').exists():continue
 h=json.loads((p/'host.json').read_text());rs=read(p/'runs.csv') if (p/'runs.csv').exists() else []
 index.append(dict(directory=p.name,exit_code=h.get('exit_code'),final=h.get('final'),failed_check_records=sum(r['status']=='failed' for r in rs),container_events='; '.join(h.get('container_events',[])),classification='recorded session' if 'overnight-session-' in p.name else 'negative control; expected rejection' if p.name.endswith('overnight-bm4') else 'correctness only' if p.name.endswith('overnight-correctness') else 'excluded failed pilot' if h.get('exit_code') else 'pilot only'))
write('attempts.csv',index)
# Historical observations use identical keys only; different build/data/caps prohibit causal speedup claims.
new=read(OUT/'sessions/headline.csv');oldp=RESULTS/'2026-11-02T004351_b53e5d0a_final';old={tuple(r[k] for k in ('output','engine','variant','clients')):r for r in read(oldp/'summary.csv')};comparison=[]
for r in new:
 key=tuple(r[k] for k in ('output','engine','variant','clients'));o=old.get(key)
 if o and (key[0].startswith('B1') or key[0].startswith('B4')):
  comparison.append(dict(output=key[0],engine=key[1],variant=key[2],clients=key[3],old_p50_ms=o['p50_ms'],new_p50_ms=r['p50_ms'],old_headline=o.get('headline'),new_headline=r.get('headline'),old_directory=oldp.name,limitation='same CPU and RAM with owner same-PC confirmation; different build/data, CPU and memory caps and pinning; historical context only'))
write('historical-common-cells.csv',comparison)
storage=[]
for label,p in [('historical',oldp)]+[(f'session-{n}',find(f'overnight-session-{n}')) for n in (1,2,3)]:
 for r in read(p/'report/B5.csv'):storage.append(dict(source=label,directory=p.name,**r))
write('historical-storage.csv',storage)
summary={'verified_sessions':len(checks),'same_source_golden_drivers_durability':True,'raw_hashes_verified':True,'all_recorded_checks_passed':True,'all_recorded_engine_exits_zero':True,'bm4':json.loads((OUT/'bm4-verification.json').read_text())['verified'],'independent_review':'not performed','validation':'passed'}
(OUT/'verification.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))

