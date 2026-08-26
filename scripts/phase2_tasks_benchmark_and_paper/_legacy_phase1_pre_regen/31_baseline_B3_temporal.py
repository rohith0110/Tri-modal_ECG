"""
13_baseline_B3.py — B3 Temporal Event Localization baseline.
Task: given raw ECG signal + query type, predict which of 10 1-second bins contain the event.
Model: ECGResNet1D encoder with 10-way sigmoid head, trained separately per query type.
Output: outputs/tables/B3_baseline_results.json
"""
import os, json, random, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader
from sklearn.metrics import average_precision_score

B3_JSONL   = "../processed/taskB_temporal_grounding.jsonl"
SIG_DIR    = "../processed/signals_lead2"
OUT_DIR    = "../outputs/tables"
MODEL_DIR  = "../outputs/model_runs/B3"
EPOCHS     = 20
BATCH      = 128
LR         = 1e-3
N_BINS     = 10
N_TRAIN    = 1500   # per query type (small — signals load from disk)
N_VAL      = 300
N_TEST     = 300
QUERY_TYPES = ["HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS"]
os.makedirs(OUT_DIR, exist_ok=True); os.makedirs(MODEL_DIR, exist_ok=True)

# ── Encoder (shared ResNet, output 512-d feature) ─────────────────────────────
class ResBlock1D(nn.Module):
    def __init__(self,a,b,s=1):
        super().__init__()
        self.c1=nn.Conv1d(a,b,7,stride=s,padding=3,bias=False); self.b1=nn.BatchNorm1d(b)
        self.c2=nn.Conv1d(b,b,7,padding=3,bias=False);           self.b2=nn.BatchNorm1d(b)
        self.sk=(nn.Sequential(nn.Conv1d(a,b,1,stride=s,bias=False),nn.BatchNorm1d(b))
                 if s!=1 or a!=b else nn.Identity())
    def forward(self,x): return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x)))))+self.sk(x))

class ResNetEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.stem=nn.Sequential(nn.Conv1d(1,64,15,2,7,bias=False),nn.BatchNorm1d(64),nn.ReLU(),nn.MaxPool1d(3,2,1))
        self.l1=nn.Sequential(ResBlock1D(64,64),ResBlock1D(64,64))
        self.l2=nn.Sequential(ResBlock1D(64,128,2),ResBlock1D(128,128))
        self.l3=nn.Sequential(ResBlock1D(128,256,2),ResBlock1D(256,256))
        self.l4=nn.Sequential(ResBlock1D(256,512,2),ResBlock1D(512,512))
    def forward(self,x): return self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1)  # (B,512)

class B3Head(nn.Module):
    def __init__(self, n_bins=10):
        super().__init__()
        self.fc = nn.Linear(512, n_bins)
    def forward(self, x): return self.fc(x)  # raw logits, apply sigmoid outside

class B3Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = ResNetEncoder()
        self.head    = B3Head(N_BINS)
    def forward(self, x): return self.head(self.encoder(x))

def load_split(jsonl_path, split, query_type, limit, seed=42):
    rng = random.Random(seed)
    recs = []
    with open(jsonl_path) as f:
        for line in f:
            r = json.loads(line)
            if r["split"] == split and r["query"] == query_type:
                recs.append(r)
    rng.shuffle(recs)
    recs = recs[:limit]

    sigs, labels = [], []
    for r in recs:
        path = os.path.join(SIG_DIR, f"{r['study_id']}.npy")
        if not os.path.exists(path): continue
        sig = np.load(path)
        if np.isnan(sig).any(): continue
        sigs.append(sig)
        labels.append(r["labels"])
    sigs   = np.array(sigs,   dtype=np.float32)
    labels = np.array(labels, dtype=np.float32)
    # z-score
    mu = sigs.mean(1,keepdims=True); sd = sigs.std(1,keepdims=True)+1e-6
    sigs = (sigs-mu)/sd
    return sigs, labels

def make_loader(sigs, labels, shuffle=False):
    ds = TensorDataset(torch.from_numpy(sigs).unsqueeze(1), torch.from_numpy(labels))
    return DataLoader(ds, batch_size=BATCH, shuffle=shuffle, num_workers=0, pin_memory=False)

def auprc_per_bin(labels, probs):
    """Mean AUPRC across bins (only bins with positive examples)."""
    aucs = []
    for b in range(N_BINS):
        if labels[:,b].sum() == 0: continue
        try: aucs.append(average_precision_score(labels[:,b], probs[:,b]))
        except: pass
    return float(np.mean(aucs)) if aucs else 0.0

def main():
    torch.manual_seed(42); np.random.seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"B3 Temporal Localization Baseline | {device}", flush=True)

    all_results = {}

    for qtype in QUERY_TYPES:
        print(f"\n--- Query: {qtype} ---", flush=True)
        t0 = time.time()

        print(f"  Loading {N_TRAIN} train / {N_VAL} val / {N_TEST} test signals...", flush=True)
        X_tr, y_tr = load_split(B3_JSONL, "train", qtype, N_TRAIN, seed=42)
        X_va, y_va = load_split(B3_JSONL, "val",   qtype, N_VAL,   seed=1)
        X_te, y_te = load_split(B3_JSONL, "test",  qtype, N_TEST,  seed=2)
        print(f"  Loaded: train={len(X_tr)}, val={len(X_va)}, test={len(X_te)}", flush=True)
        if len(X_tr) == 0:
            print("  No data — skipping", flush=True)
            continue

        tr_ldr = make_loader(X_tr, y_tr, shuffle=True)
        va_ldr = make_loader(X_va, y_va)
        te_ldr = make_loader(X_te, y_te)

        model = B3Model().to(device)
        opt   = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
        best_val, best_state, history = float("inf"), None, []

        for ep in range(1, EPOCHS+1):
            model.train(); losses=[]
            for Xb,yb in tr_ldr:
                Xb,yb=Xb.to(device),yb.to(device)
                logits=model(Xb); loss=F.binary_cross_entropy_with_logits(logits,yb)
                opt.zero_grad(); loss.backward(); opt.step()
                losses.append(loss.item())
            sched.step()
            model.eval(); vl=[]
            with torch.no_grad():
                for Xb,yb in va_ldr:
                    vl.append(F.binary_cross_entropy_with_logits(model(Xb.to(device)),yb.to(device)).item())
            vl_mean=float(np.mean(vl))
            if ep % 5 == 0 or ep == EPOCHS:
                print(f"  Ep{ep:2d}: train={np.mean(losses):.4f}  val={vl_mean:.4f}", flush=True)
            history.append({"epoch":ep,"train_loss":float(np.mean(losses)),"val_loss":vl_mean})
            if vl_mean < best_val:
                best_val=vl_mean; best_state={k:v.cpu().clone() for k,v in model.state_dict().items()}

        model.load_state_dict(best_state); model.eval()
        probs_all, labels_all = [], []
        with torch.no_grad():
            for Xb,yb in te_ldr:
                probs_all.append(torch.sigmoid(model(Xb.to(device))).cpu().numpy())
                labels_all.append(yb.numpy())
        probs_all  = np.concatenate(probs_all)
        labels_all = np.concatenate(labels_all)

        mean_auprc = auprc_per_bin(labels_all, probs_all)
        per_bin_pos = [int(labels_all[:,b].sum()) for b in range(N_BINS)]
        print(f"  Mean AUPRC (over bins): {mean_auprc:.4f}", flush=True)
        print(f"  Positive per bin: {per_bin_pos}", flush=True)

        all_results[qtype] = {
            "mean_auprc_over_bins": round(mean_auprc, 4),
            "n_test": len(X_te),
            "positives_per_bin": per_bin_pos,
            "training_time_s": round(time.time()-t0, 1),
            "history": history,
        }
        torch.save(best_state, os.path.join(MODEL_DIR, f"B3_{qtype}_model.pt"))

    out = os.path.join(OUT_DIR, "B3_baseline_results.json")
    with open(out, "w") as f: json.dump(all_results, f, indent=2)
    print(f"\nSaved: {out}", flush=True)

if __name__ == "__main__":
    main()
