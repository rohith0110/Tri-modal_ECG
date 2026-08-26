"""
11_eval_B2_regime1.py — B2 corruption curve for regime-1 (clean-trained B1 model).
Loads 2000 clean anchor signals, applies B2 corruptions in-memory (avoids 80K disk reads).
Output: outputs/tables/B2_regime1_curve.json
"""
import os, json, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from sklearn.metrics import accuracy_score, f1_score

MODEL_PATH = "../outputs/model_runs/B1/B1_seed42_model.pt"
B2_JSONL   = "../processed/taskB2_noise_robustness.jsonl"
B1_JSONL   = "../processed/taskB1_measurement_blind.jsonl"
SIG_DIR    = "../processed/signals_lead2"
OUT_DIR    = "../outputs/tables"
HR_MAP     = {"bradycardia": 0, "normal": 1, "tachycardia": 2}
FS, N_SAMP = 500, 5000
SEED       = 42
os.makedirs(OUT_DIR, exist_ok=True)

CORRUPT_TYPES = ["gaussian","baseline_wander","powerline","emg",
                 "electrode_motion","lead_dropout","gain_drift","saturation"]
SNR_LEVELS    = [30, 20, 10, 5, 0]

# ── Corruption functions (identical to task_B2.py) ───────────────────────────
def _pow(s): return np.mean(s**2)
def _scale(sig, noise, snr_db):
    p = _pow(noise)
    if p < 1e-12: return noise
    return noise * np.sqrt(_pow(sig) / (10**(snr_db/10.0)) / p)

def corrupt(sig, ctype, snr_db, rng):
    t = np.arange(N_SAMP) / FS
    if ctype == "gaussian":
        n = rng.standard_normal(N_SAMP).astype(np.float32)
        return sig + _scale(sig, n, snr_db)
    elif ctype == "baseline_wander":
        n = np.sin(2*np.pi*rng.uniform(0.05,1.0)*t + rng.uniform(0,2*np.pi)).astype(np.float32)
        return sig + _scale(sig, n, snr_db)
    elif ctype == "powerline":
        n = np.sin(2*np.pi*rng.choice([50.,60.])*t + rng.uniform(0,2*np.pi)).astype(np.float32)
        return sig + _scale(sig, n, snr_db)
    elif ctype == "emg":
        n = rng.standard_normal(N_SAMP).astype(np.float32)
        w = max(1, FS//50); k = np.ones(w,dtype=np.float32)/w
        n = n - np.convolve(n, k, mode="same")
        return sig + _scale(sig, n, snr_db)
    elif ctype == "electrode_motion":
        n = np.zeros(N_SAMP, dtype=np.float32)
        for _ in range(int(rng.integers(3,10))):
            pos = int(rng.integers(0, N_SAMP)); w = int(rng.integers(10,80))
            s0,s1 = max(0,pos-w//2), min(N_SAMP,pos+w//2)
            n[s0:s1] = rng.uniform(0.5,2.0)*np.sign(rng.standard_normal())
        return sig + _scale(sig, n, snr_db)
    elif ctype == "lead_dropout":
        frac = 0.1*(10**(-snr_db/20.0))+0.05
        L = int(N_SAMP*min(frac,0.5)); st=int(rng.integers(0,N_SAMP-L))
        out = sig.copy(); out[st:st+L]=0.0; return out
    elif ctype == "gain_drift":
        depth = np.clip(10**(-snr_db/20.0),0.01,0.99)
        env = 1.0 + depth*np.sin(2*np.pi*rng.uniform(0.01,0.5)*t + rng.uniform(0,2*np.pi))
        return (sig * env.astype(np.float32))
    elif ctype == "saturation":
        p = np.sqrt(_pow(sig)); clip_f = 10**(snr_db/20.0)*0.5
        thr = max(0.1*p, clip_f*p)
        return np.clip(sig, -thr, thr).astype(np.float32)
    return sig

# ── Model ─────────────────────────────────────────────────────────────────────
class ResBlock1D(nn.Module):
    def __init__(self,a,b,s=1):
        super().__init__()
        self.c1=nn.Conv1d(a,b,7,stride=s,padding=3,bias=False); self.b1=nn.BatchNorm1d(b)
        self.c2=nn.Conv1d(b,b,7,padding=3,bias=False);           self.b2=nn.BatchNorm1d(b)
        self.sk=(nn.Sequential(nn.Conv1d(a,b,1,stride=s,bias=False),nn.BatchNorm1d(b))
                 if s!=1 or a!=b else nn.Identity())
    def forward(self,x): return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x)))))+self.sk(x))

class ECGResNet1D(nn.Module):
    def __init__(self,nc=3):
        super().__init__()
        self.stem=nn.Sequential(nn.Conv1d(1,64,15,2,7,bias=False),nn.BatchNorm1d(64),nn.ReLU(),nn.MaxPool1d(3,2,1))
        self.l1=nn.Sequential(ResBlock1D(64,64),ResBlock1D(64,64))
        self.l2=nn.Sequential(ResBlock1D(64,128,2),ResBlock1D(128,128))
        self.l3=nn.Sequential(ResBlock1D(128,256,2),ResBlock1D(256,256))
        self.l4=nn.Sequential(ResBlock1D(256,512,2),ResBlock1D(512,512))
        self.head=nn.Linear(512,nc)
    def forward(self,x): return self.head(self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1))

def infer(model, sigs, device, batch=256):
    model.eval(); out=[]
    with torch.no_grad():
        for i in range(0,len(sigs),batch):
            Xb=torch.from_numpy(sigs[i:i+batch]).unsqueeze(1).to(device)
            out.append(torch.softmax(model(Xb),-1).cpu().numpy())
    return np.concatenate(out)

def zscore(X):
    mu=X.mean(1,keepdims=True); sd=X.std(1,keepdims=True)+1e-6
    return (X-mu)/sd

def run_curve(model_path, out_file, label):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nB2 Curve [{label}] | {device}", flush=True)

    model=ECGResNet1D(3).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device)); model.eval()

    # Label lookup from B1
    label_lookup={}
    with open(B1_JSONL) as f:
        for line in f:
            r=json.loads(line)
            if r["split"]=="test": label_lookup[r["study_id"]]=HR_MAP[r["hr_label"]]

    # Load 2000 clean anchor signals
    anchor_ids=[]
    with open(B2_JSONL) as f:
        for line in f:
            r=json.loads(line)
            if r["corruption_type"]=="clean" and r["study_id"] in label_lookup:
                anchor_ids.append(r["study_id"])

    print(f"Loading {len(anchor_ids)} clean anchor signals from signals_lead2...", flush=True)
    t0=time.time()
    clean_sigs=[]; clean_labels=[]; valid_ids=[]
    for sid in anchor_ids:
        path=os.path.join(SIG_DIR,f"{sid}.npy")
        if not os.path.exists(path): continue
        sig=np.load(path).astype(np.float32)
        if np.isnan(sig).any(): continue
        clean_sigs.append(sig); clean_labels.append(label_lookup[sid]); valid_ids.append(sid)
    clean_sigs=np.array(clean_sigs,dtype=np.float32)
    clean_labels=np.array(clean_labels,dtype=np.int64)
    print(f"  Loaded {len(clean_sigs)} anchors in {time.time()-t0:.1f}s", flush=True)

    results={}
    # Evaluate clean baseline
    probs=infer(model, zscore(clean_sigs.copy()), device)
    preds=probs.argmax(1)
    clean_acc=round(float(accuracy_score(clean_labels,preds)),4)
    clean_f1 =round(float(f1_score(clean_labels,preds,average="macro",zero_division=0)),4)
    results["clean"]={"accuracy":clean_acc,"macro_f1":clean_f1,"n":len(clean_sigs)}
    print(f"  Clean: acc={clean_acc}  f1={clean_f1}", flush=True)

    rng=np.random.default_rng(SEED)
    for ctype in CORRUPT_TYPES:
        results[ctype]={}
        for snr in SNR_LEVELS:
            corrupted=np.array([corrupt(clean_sigs[i].copy(),ctype,snr,rng) for i in range(len(clean_sigs))],dtype=np.float32)
            probs=infer(model, zscore(corrupted), device)
            preds=probs.argmax(1)
            acc=round(float(accuracy_score(clean_labels,preds)),4)
            f1 =round(float(f1_score(clean_labels,preds,average="macro",zero_division=0)),4)
            results[ctype][snr]={"accuracy":acc,"macro_f1":f1,"n":len(clean_sigs)}
            print(f"  {ctype:20s} SNR={snr:2d}dB  acc={acc:.4f}  f1={f1:.4f}", flush=True)

    with open(out_file,"w") as f: json.dump(results,f,indent=2)
    print(f"Saved: {out_file}", flush=True)
    return results

if __name__=="__main__":
    run_curve(MODEL_PATH, os.path.join(OUT_DIR,"B2_regime1_curve.json"), "regime1")
