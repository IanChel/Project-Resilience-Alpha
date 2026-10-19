"""Measure, never change: sweep `nu` and the `consecutive` rule on recorded observations and propose a pair.
Offline (no network, no Docker). It fits throwaway candidate models in memory, never touches the deployed
model, the baseline or the configuration, and writes only runtime/evidence/calibration-<UTC>.json.
The final choice is a human decision.

  python scripts/calibrate_detector.py --baseline baseline.json --attack attack.json [--normal normal.json] [--model model.joblib]

Datasets use the baseline.json format (features, rows). Get them from the detector container:
  baseline / another normal session : python -m services.detector.collect_baseline [--out ...]
  attack window, after the attack   : python -m services.detector.window export --start T --end T --out ...
then `docker compose cp detector:/models/<file> runtime/data/`. See docs/05-ML-RAG.md, section Calibration."""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.detector.model import FEATURES, MIN_BASELINE_SAMPLES, replay_alerts, score, train_model
def load_dataset(path):
    raw=Path(path).read_bytes()
    try: data=json.loads(raw)
    except ValueError: sys.exit(f'{path}: not valid JSON')
    if data.get('features')!=FEATURES: sys.exit(f'{path}: features {data.get("features")} differ from the detector {FEATURES}')
    rows=data.get('rows') or []
    if not rows or any(len(r)!=4 or not all(math.isfinite(float(v)) for v in r) for r in rows): sys.exit(f'{path}: rows must be non-empty lists of 4 finite numbers')
    stamps=data.get('timestamps')
    if stamps is not None and len(stamps)!=len(rows): sys.exit(f'{path}: timestamps and rows differ in length')
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'rows':rows,'timestamps':stamps,'window':data.get('window')}
def delay_seconds(attack,index,interval):
    """Seconds from the start of the attack window (or of the first row) to the observation that triggers the alert."""
    if index is None: return None
    stamps=attack['timestamps']
    start=(attack['window'] or {}).get('start',stamps[0] if stamps else None)
    return round(stamps[index]-start,2) if stamps and start is not None else round(index*interval,2)
def evaluate(label,nu,model,normal,attack,grid,interval):
    seen=[(score(model,r),r) for r in normal['rows']]; hit=[(score(model,r),r) for r in attack['rows']]
    negative_rate=sum(s<0 for s,_ in seen)/len(seen); results=[]
    for required in grid:
        found=replay_alerts(hit,required)
        results.append({'model':label,'nu':nu,'consecutive':required,'n_normal':len(seen),'normal_negative_score_rate':round(negative_rate,4),
            'fp_runs_ungated':replay_alerts(seen,required,gated=False)['alerts'],'fp_alerts_gated':replay_alerts(seen,required)['alerts'],
            'detected':found['first_alert_index'] is not None,'delay_s':delay_seconds(attack,found['first_alert_index'],interval)})
    return results
def pick(candidates):
    return min(candidates,key=lambda r:(r['delay_s'],r['normal_negative_score_rate'],-r['consecutive'],r['nu'])) if candidates else None
def choose(results,max_delay):
    """strict: no false alert even WITHOUT the capacity gate, detected within max_delay, fastest first.
    gate_only: same but tolerating false runs that the capacity gate would absorb (a team arbitration)."""
    fast=[r for r in results if r['detected'] and r['delay_s']<=max_delay]
    return {'strict':pick([r for r in fast if r['fp_runs_ungated']==0]),
            'gate_only':pick([r for r in fast if r['fp_alerts_gated']==0]),
            'fastest_zero_false_run':pick([r for r in results if r['detected'] and r['fp_runs_ungated']==0])}
def table(results,max_delay):
    head=f'{"model":<10}{"nu":>6}{"N":>3}{"neg%":>7}{"FPruns":>8}{"FPgate":>8}{"detect":>8}{"delay_s":>9}  target'
    lines=[head,'-'*len(head)]
    for r in results:
        ok=r['fp_runs_ungated']==0 and r['detected'] and r['delay_s']<=max_delay
        lines.append(f'{r["model"]:<10}{r["nu"]:>6g}{r["consecutive"]:>3}{100*r["normal_negative_score_rate"]:>7.1f}{r["fp_runs_ungated"]:>8}{r["fp_alerts_gated"]:>8}'
                     f'{"yes" if r["detected"] else "NO":>8}{"-" if r["delay_s"] is None else r["delay_s"]:>9}  {"OK" if ok else ""}')
    return '\n'.join(lines)
def numbers(text,cast):
    try: return [cast(x) for x in text.split(',') if x.strip()]
    except ValueError: raise argparse.ArgumentTypeError(f'not a comma-separated list of numbers: {text!r}')
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--baseline',required=True,help='normal-traffic baseline; the first 80 %% fits the candidates (as train.py)')
    p.add_argument('--attack',required=True,help='observations recorded during an attack, starting at its launch')
    p.add_argument('--normal',help='another normal session (out of sample). Default: the 20 %% holdout of the baseline, too short to conclude')
    p.add_argument('--model',help='optional deployed model.joblib, evaluated as a reference line (trusted local file only)')
    p.add_argument('--nu',type=lambda t:numbers(t,float),default=[0.01,0.02,0.03,0.05,0.08,0.1])
    p.add_argument('--consecutive',type=lambda t:numbers(t,int),default=[1,2,3,4,5,6])
    p.add_argument('--interval',type=float,default=2.0,help='seconds between observations when the attack file has no timestamps (default 2)')
    p.add_argument('--max-delay',type=float,default=10.0,help='detection target in seconds (default 10)')
    p.add_argument('--min-normal',type=int,default=150,help='observations needed to call a normal window sustained (default 150 = 5 min)')
    p.add_argument('--out-dir',type=Path,default=ROOT/'runtime'/'evidence')
    a=p.parse_args(argv)
    baseline,attack=load_dataset(a.baseline),load_dataset(a.attack)
    if len(baseline['rows'])<MIN_BASELINE_SAMPLES: sys.exit(f'Baseline has {len(baseline["rows"])} observations, at least {MIN_BASELINE_SAMPLES} required')
    cut=int(len(baseline['rows'])*0.8)
    if a.normal: normal=load_dataset(a.normal); normal_source='second normal session'
    else: normal={'path':None,'sha256':None,'rows':baseline['rows'][cut:]}; normal_source='baseline holdout'
    warnings=[]
    if len(normal['rows'])<a.min_normal: warnings.append(f'Only {len(normal["rows"])} normal observations ({normal_source}); at least {a.min_normal} (about 5 min) are needed to claim zero false positives on sustained normal traffic. Result NOT conclusive: record another normal session and pass it with --normal.')
    if not any(r[2]>0 for r in attack['rows']): warnings.append('The attack window contains no capacity rejection (capacity_denied_10s is always 0): the alert rule cannot fire on it. Check the window bounds.')
    if any(r[2]>0 for r in normal['rows']): warnings.append('The normal series contains capacity rejections: it is not clean normal traffic.')
    results=[]
    for nu in a.nu:
        try: candidate=train_model(baseline['rows'][:cut],nu)
        except ValueError as exc: sys.exit(f'Baseline refused for nu={nu:g}: {exc}')
        results+=evaluate('candidate',nu,candidate,normal,attack,a.consecutive,a.interval)
    deployed=[]
    if a.model:
        import joblib
        model=joblib.load(a.model)
        deployed=evaluate('deployed',round(float(model[-1].nu),6),model,normal,attack,a.consecutive,a.interval)
    chosen=choose(results,a.max_delay); conclusive=len(normal['rows'])>=a.min_normal
    print(table(results+deployed,a.max_delay))
    print(f'\nNormal series: {len(normal["rows"])} observations ({normal_source}). Attack series: {len(attack["rows"])} observations.')
    print('FPruns = runs of N negative scores on normal traffic, WITHOUT the capacity gate (robustness of the pair on its own).')
    print('FPgate = alerts the real rule would fire on the same traffic (negative score AND capacity rejections). target = FPruns 0, detected, delay <= '+f'{a.max_delay:g} s.')
    for w in warnings: print('WARNING:',w)
    best=chosen['strict']
    if best: print(f'\nPROPOSAL: nu={best["nu"]:g}, consecutive={best["consecutive"]} (detected in {best["delay_s"]} s, {best["fp_runs_ungated"]} false run on {best["n_normal"]} normal observations)'+('' if conclusive else ' - NOT conclusive'))
    else:
        print(f'\nNO PAIR meets both targets (zero false run and detection within {a.max_delay:g} s): team arbitration needed.')
        z=chosen['fastest_zero_false_run']; g=chosen['gate_only']
        print('  Zero false run, fastest detection: '+(f'nu={z["nu"]:g}, consecutive={z["consecutive"]}, {z["delay_s"]} s' if z else 'none detects the attack'))
        print('  Relying on the capacity gate alone: '+(f'nu={g["nu"]:g}, consecutive={g["consecutive"]}, {g["delay_s"]} s (tolerates {g["fp_runs_ungated"]} false run(s) the gate would absorb)' if g else 'none'))
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    a.out_dir.mkdir(parents=True,exist_ok=True); path=a.out_dir/f'calibration-{stamp}.json'
    path.write_text(json.dumps({'created_at':stamp,'inputs':{'baseline':{k:baseline[k] for k in ('path','sha256')},'attack':{k:attack[k] for k in ('path','sha256')},
        'normal':{'source':normal_source,'path':normal['path'],'sha256':normal['sha256'],'n':len(normal['rows'])},'model':a.model},
        'parameters':{'nu':a.nu,'consecutive':a.consecutive,'interval_s':a.interval,'max_delay_s':a.max_delay,'min_normal':a.min_normal,'split':f'first {cut} of {len(baseline["rows"])} baseline rows fit each candidate'},
        'results':results,'deployed':deployed,'proposal':chosen['strict'],'proposal_if_gate_only':chosen['gate_only'],'fastest_zero_false_run':chosen['fastest_zero_false_run'],
        'conclusive':conclusive,'warnings':warnings,
        'notes':['Candidates are fitted in memory for each nu; the deployed model, the baseline and the configuration are never modified.',
                 'The 30 s alert cooldown is not modelled: the counter restarts after each alert.',
                 'Delay runs from the attack window start (or first row) to the observation that triggers the alert; it excludes alert delivery and remediation.']},indent=2))
    print(f'\nEvidence: {path}')
    return 0 if best and conclusive else 1
if __name__=='__main__': sys.exit(main())
