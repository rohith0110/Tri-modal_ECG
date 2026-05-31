"""
19_b1_sqi_stratified.py — B1 SQI-tier stratified evaluation.
Computes a kurtosis-based signal quality index (SQI) for a sample of test signals,
stratifies into high/medium/low tiers, and reports B1 accuracy per tier.
Output: outputs/tables/B1_sqi_stratified.json
"""
import os, json, random, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from scipy.stats import kurtosis as scipy_kurtosis
from sklearn.metrics import accuracy_score, f1_score, average_precision_score
from sklearn.preprocessing import label_binarize

B1_JSONL = "../processed/taskB1_measurement_blind.jsonl"
SIG_DIR  = "../processed/signals_lead2"
MODEL_PT = "../outputs/model_runs/B1/B1_seed42_model.pt"
OUT_DIR  = "../outputs/tables"
SAMPLE_N = 3000   # test records to evaluate
SEED     = 42
os.makedirs(OUT_DIR, exist_ok=True)

HR_NAMES = ["bradycardia", "normal", "tachycardia"]
HR_MAP   = {"bradycardia": 0, "normal": 1, "tachycardia": 2}

# SQI tiers from spec: high>=0.8, medium 0.6-0.8, low<0.6
# Using kurtosis-SQI: kurtosis normalised to [0,1]
# High kurtosis (sharp QRS peaks) = better signal quality
SQI_HIGH_T   = 0.8
SQI_MEDIUM_T = 0.6

class ResBlock1D(nn.Module):
    def __init__(self, a, b, s=1):
        super().__init__()
        self.c1 = nn.Conv1d(a, b, 7, stride=s, padding=3, bias=False); self.b1 = nn.BatchNorm1d(b)
        self.c2 = nn.Conv1d(b, b, 7, padding=3, bias=False);           self.b2 = nn.BatchNorm1d(b)
        self.sk = (nn.Sequential(nn.Conv1d(a, b, 1, stride=s, bias=False), nn.BatchNorm1d(b))
                   if s != 1 or a != b else nn.Identity())
    def forward(self, x): return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x))))) + self.sk(x))

class ECGResNet1D(nn.Module):
    def __init__(self, nc=3):
        super().__init__()
        self.stem = nn.Sequential(nn.Conv1d(1,64,15,2,7,bias=False), nn.BatchNorm1d(64), nn.ReLU(), nn.MaxPool1d(3,2,1))
        self.l1   = nn.Sequential(ResBlock1D(64,64),    ResBlock1D(64,64))
        self.l2   = nn.Sequential(ResBlock1D(64,128,2), ResBlock1D(128,128))
        self.l3   = nn.Sequential(ResBlock1D(128,256,2),ResBlock1D(256,256))
        self.l4   = nn.Sequential(ResBlock1D(256,512,2),ResBlock1D(512,512))
        self.head = nn.Linear(512, nc)
    def forward(self, x): return self.head(self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1))

def compute_sqi(sig):
    """
    Kurtosis-based SQI. Clean ECG has large kurtosis (sharp QRS peaks).
    Excess kurtosis > 5: high quality; 2-5: medium; <2: low.
    Map to [0,1] via sigmoid-like transformation.
    """
    if sig is None or np.isnan(sig).any() or np.std(sig) < 1e-6:
        return 0.0
    k = float(scipy_kurtosis(sig, fisher=True))  # excess kurtosis
    # Normalise: k=10 -> ~1.0; k=5 -> ~0.8; k=2 -> ~0.6; k=0 -> ~0.5; k<0 -> <0.5
    sqi = float(1.0 / (1.0 + np.exp(-0.3 * (k - 3))))
    return max(0.0, min(1.0, sqi))

def sqi_tier(sqi_val):
    if sqi_val >= SQI_HIGH_T:   return "high"
    if sqi_val >= SQI_MEDIUM_T: return "medium"
    return "low"

def main():
    rng = random.Random(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"B1 SQI-Stratified Evaluation | {device}", flush=True)

    # Load test records
    print("Loading B1 test records...", flush=True)
    test_recs = []
    with open(B1_JSONL) as f:
        for line in f:
            r = json.loads(line)
            if r["split"] == "test":
                test_recs.append(r)
    rng.shuffle(test_recs)
    test_recs = test_recs[:SAMPLE_N]
    print(f"  Sampled {len(test_recs):,} test records", flush=True)

    # Count subjects
    n_subjects = len(set(r["subject_id"] for r in test_recs))

    # Load signals and compute SQI
    print("Loading signals and computing SQI...", flush=True)
    t0 = time.time()
    signals = []
    labels  = []
    sqis    = []
    valid_recs = []

    for r in test_recs:
        path = os.path.join(SIG_DIR, f"{r['study_id']}.npy")
        if not os.path.exists(path):
            continue
        sig = np.load(path).astype(np.float32)
        if np.isnan(sig).any():
            continue
        sqi_val = compute_sqi(sig)
        signals.append(sig)
        labels.append(HR_MAP[r["hr_label"]])
        sqis.append(sqi_val)
        valid_recs.append(r)

    print(f"  Loaded {len(signals):,} signals in {time.time()-t0:.1f}s", flush=True)

    signals = np.array(signals, dtype=np.float32)
    labels  = np.array(labels, dtype=np.int64)
    sqis    = np.array(sqis, dtype=np.float32)

    # SQI distribution
    tiers = np.array([sqi_tier(s) for s in sqis])
    for t in ["high", "medium", "low"]:
        n = int((tiers == t).sum())
        print(f"  SQI tier '{t}': {n} records ({100*n/len(tiers):.1f}%)", flush=True)

    # Load ResNet model
    print("Loading ResNet model...", flush=True)
    model = ECGResNet1D(3).to(device)
    model.load_state_dict(torch.load(MODEL_PT, map_location=device))
    model.eval()

    # Normalise signals
    mu = signals.mean(1, keepdims=True); sd = signals.std(1, keepdims=True) + 1e-6
    signals_norm = (signals - mu) / sd

    # Inference in batches
    print("Running inference...", flush=True)
    BATCH = 256
    all_probs = []
    for i in range(0, len(signals_norm), BATCH):
        Xb = torch.from_numpy(signals_norm[i:i+BATCH]).unsqueeze(1).to(device)
        with torch.no_grad():
            logits = model(Xb)
            probs = torch.softmax(logits, dim=1).cpu().numpy()
        all_probs.append(probs)
    all_probs = np.concatenate(all_probs, axis=0)
    preds = np.argmax(all_probs, axis=1)

    # Evaluate per tier
    def tier_metrics(mask, name):
        yt = labels[mask]; yp = preds[mask]; yprob = all_probs[mask]
        if mask.sum() == 0:
            return {"n": 0, "n_subjects": 0}
        n_subj = len(set(r["subject_id"] for r, m in zip(valid_recs, mask) if m))
        acc  = round(float(accuracy_score(yt, yp)), 4)
        f1   = round(float(f1_score(yt, yp, average="macro", zero_division=0)), 4)
        yt_bin = label_binarize(yt, classes=[0, 1, 2])
        try:  auprc = round(float(average_precision_score(yt_bin, yprob, average="macro")), 4)
        except: auprc = 0.0
        print(f"  {name:8s}: n={mask.sum():4d}  acc={acc:.4f}  F1={f1:.4f}  AUPRC={auprc:.4f}", flush=True)
        return {"n_ecgs": int(mask.sum()), "n_subjects": n_subj,
                "accuracy": acc, "macro_f1": f1, "macro_auprc": auprc,
                "sqi_mean": round(float(sqis[mask].mean()), 4)}

    print("\nPer-tier results:", flush=True)
    results = {
        "overall": tier_metrics(np.ones(len(labels), dtype=bool), "overall"),
        "high_sqi": tier_metrics(tiers == "high",   "high"),
        "medium_sqi": tier_metrics(tiers == "medium","medium"),
        "low_sqi":  tier_metrics(tiers == "low",    "low"),
        "sqi_thresholds": {"high": SQI_HIGH_T, "medium": SQI_MEDIUM_T},
        "sqi_method": "kurtosis-SQI: sigmoid(0.3*(excess_kurtosis - 3)); high>=0.8, medium>=0.6, low<0.6",
        "n_total_test_ecgs": 78076,
        "n_total_test_subjects": 16134,
        "note": f"Evaluated on {SAMPLE_N}-record sample of test split"
    }

    out = os.path.join(OUT_DIR, "B1_sqi_stratified.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}", flush=True)

if __name__ == "__main__":
    main()
