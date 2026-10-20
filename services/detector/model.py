import math
import os
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM
FEATURES=['quote_rate','active_work','capacity_denied_10s','denial_logs_10s']
# train.py fits on the first 80 % and keeps the rest as holdout; train_model needs >= 60 rows.
MIN_BASELINE_SAMPLES=75
# Tunable without rebuilding the image: DETECTOR_NU (training time) and DETECTOR_CONSECUTIVE (runtime).
DEFAULT_NU=0.02   # calibre le 20/10 (156 obs normales) : 0 fausse serie avec consecutive=3 ; voir docs/05-ML-RAG.md
DEFAULT_CONSECUTIVE=3
def check_nu(nu):
    if not 0<nu<=1: raise ValueError(f'nu must be in ]0, 1], got {nu}')
    return float(nu)
def nu_from_env():
    raw=os.getenv('DETECTOR_NU')
    try: return check_nu(DEFAULT_NU if raw in (None,'') else float(raw))
    except ValueError: raise ValueError(f'DETECTOR_NU must be a number in ]0, 1], got {raw!r}') from None
def consecutive_from_env():
    raw=os.getenv('DETECTOR_CONSECUTIVE')
    try: value=DEFAULT_CONSECUTIVE if raw in (None,'') else int(raw)
    except ValueError: raise ValueError(f'DETECTOR_CONSECUTIVE must be an integer >= 1, got {raw!r}') from None
    if value<1: raise ValueError(f'DETECTOR_CONSECUTIVE must be an integer >= 1, got {raw!r}')
    return value
def train_model(rows,nu=None):
    nu=check_nu(nu_from_env() if nu is None else nu)
    x=np.asarray(rows,dtype=float)
    if x.ndim!=2 or x.shape[1]!=4 or len(x)<60 or not np.isfinite(x).all():
        raise ValueError('At least 60 finite 4-feature live observations required')
    if (x[:,2:]!=0).any():
        raise ValueError('Baseline contains overload: refused to train')
    return make_pipeline(StandardScaler(),OneClassSVM(kernel='rbf',gamma='scale',nu=nu)).fit(x)
def score(model,row):
    if len(row)!=4 or not all(math.isfinite(float(v)) for v in row):
        raise ValueError('Invalid telemetry')
    return float(model.decision_function([row])[0])
def is_anomalous(value,row):
    """The one definition of an anomalous observation: model novelty (negative score) AND
    capacity rejections present. It feeds the alert counter and GET /anomaly alike."""
    return value<0 and row[2]>0
def next_consecutive(consecutive,value,row):
    """The one counter rule used by the alert loop and by the calibration replay."""
    return consecutive+1 if is_anomalous(value,row) else 0
def alert_due(consecutive,required):
    return consecutive>=required
def replay_alerts(observations,required,gated=True):
    """Replay the alert rule over (score, row) pairs in time order, as the detector loop would, minus the
    30 s cooldown. The counter restarts after each alert. gated=False drops the capacity condition and
    counts runs of negative scores only: it measures the model and `required` on their own."""
    consecutive=0; first=None; alerts=0
    for i,(value,row) in enumerate(observations):
        consecutive=next_consecutive(consecutive,value,row) if gated else (consecutive+1 if value<0 else 0)
        if alert_due(consecutive,required):
            alerts+=1; first=i if first is None else first; consecutive=0
    return {'alerts':alerts,'first_alert_index':first}
