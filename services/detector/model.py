import math
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM
FEATURES=['quote_rate','active_work','capacity_denied_10s','denial_logs_10s']
# train.py fits on the first 80 % and keeps the rest as holdout; train_model needs >= 60 rows.
MIN_BASELINE_SAMPLES=75
def train_model(rows):
    x=np.asarray(rows,dtype=float)
    if x.ndim!=2 or x.shape[1]!=4 or len(x)<60 or not np.isfinite(x).all():
        raise ValueError('At least 60 finite 4-feature live observations required')
    if (x[:,2:]!=0).any():
        raise ValueError('Baseline contains overload: refused to train')
    return make_pipeline(StandardScaler(),OneClassSVM(kernel='rbf',gamma='scale',nu=0.03)).fit(x)
def score(model,row):
    if len(row)!=4 or not all(math.isfinite(float(v)) for v in row):
        raise ValueError('Invalid telemetry')
    return float(model.decision_function([row])[0])
def is_anomalous(value,row):
    """The one definition of an anomalous observation: model novelty (negative score) AND
    capacity rejections present. It feeds the alert counter and GET /anomaly alike."""
    return value<0 and row[2]>0
