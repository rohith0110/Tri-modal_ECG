"""
08_train_ram.py — RAM-preloaded ResNet training (solves Windows small-file I/O bottleneck)
Loads all split signals into memory upfront → pure GPU training, no disk I/O during epochs.
Uses 10K/2K/2K (train/val/test) subset for fast demo; set FULL_DATASET=True for full run.
"""

import os, json, argparse, random
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score
from sklearn.preprocessing import label_binarize
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
B1_PATH      = "../processed/taskB1_measurement_blind.jsonl"
OUT_DIR      = "../outputs/model_runs/B1"
FULL_DATASET = False    # True = use all records (~4.8 GB RAM); False = 10K/2K/2K subset
TRAIN_N      = 10000 if not True else None   # will be set below
VAL_N        = 2000
TEST_N       = 2000
EPOCHS       = 20
BATCH_SIZE   = 512
LR           = 1e-3
os.makedirs(OUT_DIR, exist_ok=True)

HR_MAP   = {"bradycardia": 0, "normal": 1, "tachycardia": 2}
HR_NAMES = ["bradycardia", "normal", "tachycardia"]

# ── Architecture ──────────────────────────────────────────────────────────────
class ResBlock1D(nn.Module):
    def __init__(self, a, b, s=1):
        super().__init__()
        self.c1 = nn.Conv1d(a,b,7,stride=s,padding=3,bias=False); self.b1=nn.BatchNorm1d(b)
        self.c2 = nn.Conv1d(b,b,7,padding=3,bias=False);           self.b2=nn.BatchNorm1d(b)
        self.sk = (nn.Sequential(nn.Conv1d(a,b,1,stride=s,bias=False),nn.BatchNorm1d(b))
                   if s!=1 or a!=b else nn.Identity())
    def forward(self,x): return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x)))))+self.sk(x))

class ECGResNet1D(nn.Module):
    def __init__(self,nc=3):
        super().__init__()
        self.stem  = nn.Sequential(nn.Conv1d(1,64,15,2,7,bias=False),nn.BatchNorm1d(64),nn.ReLU(),nn.MaxPool1d(3,2,1))
        self.l1    = nn.Sequential(ResBlock1D(64,64),  ResBlock1D(64,64))
        self.l2    = nn.Sequential(ResBlock1D(64,128,2),ResBlock1D(128,128))
        self.l3    = nn.Sequential(ResBlock1D(128,256,2),ResBlock1D(256,256))
        self.l4    = nn.Sequential(ResBlock1D(256,512,2),ResBlock1D(512,512))
        self.head  = nn.Linear(512,nc)
    def forward(self,x):
        return self.head(self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1))

# ── Bootstrap CI ─────────────────────────────────────────────────────────────
def bootstrap_auprc(yt, ys, n=1000, seed=0):
    rng=np.random.default_rng(seed); N=len(yt); aucs=[]
    for _ in range(n):
        idx=rng.integers(0,N,N)
        try: aucs.append(average_precision_score(yt[idx],ys[idx],average="macro"))
        except: pass
    a=np.array(aucs)
    return float(a.mean()),float(np.percentile(a,2.5)),float(np.percentile(a,97.5))

# ── Load records and signals into RAM ─────────────────────────────────────────
def load_to_ram(path, split, limit=None):
    print(f"  Scanning {split}...")
    recs=[]
    with open(path) as f:
        for line in f:
            r=json.loads(line)
            if r["split"]==split: recs.append(r)
    if limit: random.shuffle(recs); recs=recs[:limit]
    print(f"  Loading {len(recs):,} signals into RAM...")
    sigs   = np.zeros((len(recs),5000), dtype=np.float32)
    labels = np.zeros(len(recs),        dtype=np.int64)
    for i,r in enumerate(tqdm(recs, desc=f"  {split}", leave=False)):
        sigs[i]   = np.load(r["signal_path"])
        labels[i] = HR_MAP[r["hr_label"]]
        if (i+1)%5000==0: print(f"    {i+1}/{len(recs)}")
    return sigs, labels, recs

# ── Main ──────────────────────────────────────────────────────────────────────
def main(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}\nB1 ResNet (RAM-preloaded) | Seed {seed} | {device}\n{'='*60}")

    print("Preloading signals into RAM...")
    tr_n = None if FULL_DATASET else TRAIN_N
    va_n = None if FULL_DATASET else VAL_N
    te_n = None if FULL_DATASET else TEST_N

    X_tr, y_tr, _ = load_to_ram(B1_PATH, "train", tr_n)
    X_va, y_va, _ = load_to_ram(B1_PATH, "val",   va_n)
    X_te, y_te, te_recs = load_to_ram(B1_PATH, "test",  te_n)
    print(f"RAM loaded — train:{len(X_tr):,}  val:{len(X_va):,}  test:{len(X_te):,}")

    # Normalize per-sample (z-score)
    mu = X_tr.mean(axis=1, keepdims=True); sd = X_tr.std(axis=1, keepdims=True)+1e-6
    X_tr = (X_tr-mu)/sd
    mu_va = X_va.mean(axis=1,keepdims=True); sd_va=X_va.std(axis=1,keepdims=True)+1e-6
    X_va = (X_va-mu_va)/sd_va
    mu_te = X_te.mean(axis=1,keepdims=True); sd_te=X_te.std(axis=1,keepdims=True)+1e-6
    X_te = (X_te-mu_te)/sd_te

    def make_loader(X, y, shuffle=False, aug=False):
        Xt = torch.from_numpy(X).unsqueeze(1)   # (N,1,5000)
        yt = torch.from_numpy(y)
        ds = TensorDataset(Xt, yt)
        return DataLoader(ds, batch_size=BATCH_SIZE, shuffle=shuffle, num_workers=0, pin_memory=(device.type=="cuda"))

    tr_loader = make_loader(X_tr, y_tr, shuffle=True,  aug=True)
    va_loader = make_loader(X_va, y_va, shuffle=False)
    te_loader = make_loader(X_te, y_te, shuffle=False)

    model = ECGResNet1D(nc=3).to(device)
    opt   = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
    best_val, best_state, history = float("inf"), None, []

    print(f"\nTraining {EPOCHS} epochs...")
    for epoch in range(1, EPOCHS+1):
        model.train()
        losses=[]
        for Xb, yb in tr_loader:
            Xb,yb = Xb.to(device), yb.to(device)
            # Light augmentation on GPU
            Xb = Xb * (0.85 + 0.30*torch.rand(Xb.size(0),1,1,device=device))
            loss=F.cross_entropy(model(Xb),yb)
            opt.zero_grad(); loss.backward(); opt.step()
            losses.append(loss.item())
        sched.step()

        model.eval()
        vl=[]
        with torch.no_grad():
            for Xb,yb in va_loader:
                vl.append(F.cross_entropy(model(Xb.to(device)),yb.to(device)).item())
        val_loss=float(np.mean(vl))
        print(f"  Ep{epoch:2d}: train={np.mean(losses):.4f}  val={val_loss:.4f}")
        history.append({"epoch":epoch,"train_loss":float(np.mean(losses)),"val_loss":val_loss})

        if val_loss<best_val:
            best_val=val_loss
            best_state={k:v.cpu().clone() for k,v in model.state_dict().items()}

    # ── Test ─────────────────────────────────────────────────────────────────
    model.load_state_dict(best_state); model.eval()
    logits_all, labels_all = [], []
    with torch.no_grad():
        for Xb,yb in te_loader:
            logits_all.append(model(Xb.to(device)).cpu().numpy())
            labels_all.append(yb.numpy())
    logits=np.concatenate(logits_all); labels=np.concatenate(labels_all)
    probs=torch.softmax(torch.from_numpy(logits),-1).numpy()
    preds=probs.argmax(1)

    labels_bin=label_binarize(labels,classes=[0,1,2])
    auprc,ci_lo,ci_hi=bootstrap_auprc(labels_bin,probs)
    auroc=roc_auc_score(labels_bin,probs,average="macro",multi_class="ovr")
    f1   =f1_score(labels,preds,average="macro",zero_division=0)
    acc  =float((labels==preds).mean())
    n_pc ={c:int((labels==i).sum()) for i,c in enumerate(HR_NAMES)}

    result={
        "task":"B1_hr_label","seed":seed,"model":"ECGResNet1D_1lead",
        "n_test_ecg":int(len(labels)),"n_test_subjects":"see splits_subject_level.parquet",
        "n_per_class":n_pc,
        "macro_auprc":round(auprc,4),"auprc_ci_95":[round(ci_lo,4),round(ci_hi,4)],
        "macro_auroc":round(auroc,4),"macro_f1":round(f1,4),"accuracy":round(acc,4),
        "training_history":history,
        "training_subset":f"{len(X_tr):,} train / {len(X_va):,} val / {len(X_te):,} test",
        "full_dataset":FULL_DATASET,
    }
    out=os.path.join(OUT_DIR,f"B1_seed{seed}_results.json")
    with open(out,"w") as f: json.dump(result,f,indent=2)

    print(f"\n{'='*60}")
    print(f"  AUPRC: {auprc:.4f}  [{ci_lo:.4f}, {ci_hi:.4f}]")
    print(f"  AUROC: {auroc:.4f}  F1: {f1:.4f}  Acc: {acc:.4f}")
    print(f"  Class counts: {n_pc}")
    print(f"  Saved: {out}")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--full",action="store_true",help="Use full dataset (needs ~5GB RAM)")
    args=p.parse_args()
    if args.full:
        FULL_DATASET=True
    main(args.seed)
