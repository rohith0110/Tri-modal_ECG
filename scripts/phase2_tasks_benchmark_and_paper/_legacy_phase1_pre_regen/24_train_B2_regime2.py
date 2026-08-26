"""
12_train_regime2.py — B2 Regime 2: ResNet trained with noise augmentation matching B2 corruption families.
Saves model weights; run 11b_eval_B2_regime2.py afterward to get the corruption curve.
Usage: python 12_train_regime2.py --seed 42
"""
import os, json, argparse, random, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score
from sklearn.preprocessing import label_binarize

BANK_DIR = "../processed/signal_bank"
OUT_DIR  = "../outputs/model_runs/B2_regime2"
EPOCHS, BATCH, LR = 25, 256, 1e-3
HR_NAMES = ["bradycardia", "normal", "tachycardia"]
FS = 500  # Hz
os.makedirs(OUT_DIR, exist_ok=True)

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
    def __init__(self, nc=3):
        super().__init__()
        self.stem = nn.Sequential(nn.Conv1d(1,64,15,2,7,bias=False),nn.BatchNorm1d(64),nn.ReLU(),nn.MaxPool1d(3,2,1))
        self.l1   = nn.Sequential(ResBlock1D(64,64),    ResBlock1D(64,64))
        self.l2   = nn.Sequential(ResBlock1D(64,128,2), ResBlock1D(128,128))
        self.l3   = nn.Sequential(ResBlock1D(128,256,2),ResBlock1D(256,256))
        self.l4   = nn.Sequential(ResBlock1D(256,512,2),ResBlock1D(512,512))
        self.head = nn.Linear(512,nc)
    def forward(self,x):
        return self.head(self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1))

# ── B2 noise augmentations (numpy, applied per batch on CPU) ─────────────────
def snr_to_sigma(signal, snr_db):
    sig_power = np.mean(signal ** 2) + 1e-10
    noise_power = sig_power / (10 ** (snr_db / 10))
    return float(np.sqrt(noise_power))

def augment_batch_numpy(X, rng):
    """Apply one random B2-style corruption to each sample. X: (N, 5000) float32."""
    N, L = X.shape
    corruptions = ["gaussian", "baseline_wander", "powerline", "emg",
                   "electrode_motion", "lead_dropout", "gain_drift", "saturation", "clean"]
    out = X.copy()
    for i in range(N):
        ctype = corruptions[rng.integers(0, len(corruptions))]
        if ctype == "clean":
            continue
        snr = float(rng.choice([0, 5, 10, 20, 30]))
        sig = X[i]
        sigma = snr_to_sigma(sig, snr)
        if ctype == "gaussian":
            out[i] = sig + rng.standard_normal(L).astype(np.float32) * sigma
        elif ctype == "baseline_wander":
            t = np.linspace(0, 10, L)
            freq = rng.uniform(0.05, 1.0)
            out[i] = sig + (sigma * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        elif ctype == "powerline":
            t = np.linspace(0, 10, L)
            freq = float(rng.choice([50, 60]))
            out[i] = sig + (sigma * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        elif ctype == "emg":
            noise = rng.standard_normal(L).astype(np.float32)
            # high-pass: just use the sign pattern to approximate high-freq noise
            from scipy.signal import butter, filtfilt
            try:
                b, a = butter(4, 100.0 / (FS / 2), btype="high")
                noise = filtfilt(b, a, noise).astype(np.float32)
            except Exception:
                pass
            noise = noise / (np.std(noise) + 1e-10) * sigma
            out[i] = sig + noise
        elif ctype == "electrode_motion":
            n_spikes = int(rng.integers(3, 10))
            result = sig.copy()
            spike_amp = sigma * 3
            for _ in range(n_spikes):
                pos = int(rng.integers(0, L - 100))
                width = int(rng.integers(10, 80))
                spike = np.zeros(L, dtype=np.float32)
                spike[pos:pos+width] = spike_amp * float(rng.choice([-1, 1]))
                result += spike
            out[i] = result
        elif ctype == "lead_dropout":
            drop_len = int(L * max(0.05, min(0.6, 1 / (snr / 10 + 1))))
            start = int(rng.integers(0, L - drop_len))
            result = sig.copy(); result[start:start+drop_len] = 0.0
            out[i] = result
        elif ctype == "gain_drift":
            t = np.linspace(0, 10, L)
            freq = rng.uniform(0.01, 0.5)
            mod = 1.0 + 0.1 * np.sin(2 * np.pi * freq * t).astype(np.float32)
            out[i] = (sig * mod).astype(np.float32)
        elif ctype == "saturation":
            clip_val = np.percentile(np.abs(sig), max(10, 100 - snr * 2))
            out[i] = np.clip(sig, -clip_val, clip_val).astype(np.float32)
    return out

# ── Metrics ───────────────────────────────────────────────────────────────────
def bootstrap_auprc(yt, ys, n=1000, seed=0):
    rng = np.random.default_rng(seed); N = len(yt); aucs = []
    for _ in range(n):
        idx = rng.integers(0, N, N)
        try: aucs.append(average_precision_score(yt[idx], ys[idx], average="macro"))
        except: pass
    a = np.array(aucs)
    return float(a.mean()), float(np.percentile(a,2.5)), float(np.percentile(a,97.5))

# ── Main ──────────────────────────────────────────────────────────────────────
def main(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.backends.cudnn.benchmark = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    rng = np.random.default_rng(seed)
    print(f"\n{'='*60}\nB2 Regime-2 ResNet | Seed {seed} | {device}\n{'='*60}", flush=True)

    X_tr = np.load(f"{BANK_DIR}/train_signals.npy"); y_tr = np.load(f"{BANK_DIR}/train_labels.npy")
    X_va = np.load(f"{BANK_DIR}/val_signals.npy");   y_va = np.load(f"{BANK_DIR}/val_labels.npy")
    X_te = np.load(f"{BANK_DIR}/test_signals.npy");  y_te = np.load(f"{BANK_DIR}/test_labels.npy")

    for name, Xs, ys in [("tr",X_tr,y_tr),("va",X_va,y_va),("te",X_te,y_te)]:
        bad = int(np.isnan(Xs).any(axis=1).sum())
        if bad: print(f"  Dropped {bad} NaN from {name}", flush=True)
    mask_tr = ~np.isnan(X_tr).any(axis=1); X_tr, y_tr = X_tr[mask_tr], y_tr[mask_tr]
    mask_va = ~np.isnan(X_va).any(axis=1); X_va, y_va = X_va[mask_va], y_va[mask_va]
    mask_te = ~np.isnan(X_te).any(axis=1); X_te, y_te = X_te[mask_te], y_te[mask_te]
    print(f"Bank: train:{len(X_tr):,}  val:{len(X_va):,}  test:{len(X_te):,}", flush=True)

    for X in [X_tr, X_va, X_te]:
        mu = X.mean(1, keepdims=True); sd = X.std(1, keepdims=True) + 1e-6
        X[:] = (X - mu) / sd

    def loader(X, y, shuffle=False):
        ds = TensorDataset(torch.from_numpy(X).unsqueeze(1), torch.from_numpy(y))
        return DataLoader(ds, batch_size=BATCH, shuffle=shuffle, num_workers=0, pin_memory=False)

    va_ldr = loader(X_va, y_va); te_ldr = loader(X_te, y_te)

    model = ECGResNet1D(3).to(device)
    opt   = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)

    if device.type == "cuda":
        print("Warmup...", flush=True)
        dummy = torch.randn(BATCH,1,5000,device=device)
        dummy_y = torch.zeros(BATCH,dtype=torch.long,device=device)
        model.train(); out=model(dummy); loss=F.cross_entropy(out,dummy_y)
        opt.zero_grad(); loss.backward(); opt.step(); torch.cuda.synchronize()
        model = ECGResNet1D(3).to(device); opt = torch.optim.AdamW(model.parameters(),lr=LR,weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=EPOCHS)
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
        print("Warmup done", flush=True)

    best_val, best_state, history = float("inf"), None, []
    print(f"Training {EPOCHS} epochs with B2 noise augmentation...", flush=True)

    for ep in range(1, EPOCHS+1):
        model.train(); losses = []
        # Manual batch loop with numpy augmentation
        idx = rng.permutation(len(X_tr))
        for start in range(0, len(idx), BATCH):
            batch_idx = idx[start:start+BATCH]
            Xb_np = augment_batch_numpy(X_tr[batch_idx], rng)
            # Re-zscore after augmentation
            mu = Xb_np.mean(1, keepdims=True); sd = Xb_np.std(1, keepdims=True) + 1e-6
            Xb_np = (Xb_np - mu) / sd
            Xb = torch.from_numpy(Xb_np).unsqueeze(1).to(device)
            yb = torch.from_numpy(y_tr[batch_idx]).to(device)
            loss = F.cross_entropy(model(Xb), yb)
            opt.zero_grad(); loss.backward(); opt.step()
            losses.append(loss.item())
        sched.step()
        model.eval(); vl = []
        with torch.no_grad():
            for Xb,yb in va_ldr:
                vl.append(F.cross_entropy(model(Xb.to(device)),yb.to(device)).item())
        vl_mean = float(np.mean(vl))
        print(f"  Ep{ep:2d}/{EPOCHS}: train={np.mean(losses):.4f}  val={vl_mean:.4f}", flush=True)
        history.append({"epoch":ep,"train_loss":float(np.mean(losses)),"val_loss":vl_mean})
        if vl_mean < best_val:
            best_val = vl_mean; best_state = {k:v.cpu().clone() for k,v in model.state_dict().items()}

    model.load_state_dict(best_state); model.eval()
    logits_all, labels_all = [], []
    with torch.no_grad():
        for Xb,yb in te_ldr:
            logits_all.append(model(Xb.to(device)).cpu().numpy())
            labels_all.append(yb.numpy())
    logits=np.concatenate(logits_all); labels=np.concatenate(labels_all)
    probs=torch.softmax(torch.from_numpy(logits),-1).numpy(); preds=probs.argmax(1)
    labels_bin=label_binarize(labels,classes=[0,1,2])
    auprc,ci_lo,ci_hi=bootstrap_auprc(labels_bin,probs)
    auroc=roc_auc_score(labels_bin,probs,average="macro",multi_class="ovr")
    f1=f1_score(labels,preds,average="macro",zero_division=0)
    acc=float((labels==preds).mean())

    result={"task":"B2_regime2","seed":seed,"model":"ECGResNet1D_1lead_noise_aug",
            "macro_auprc":round(auprc,4),"auprc_ci_95":[round(ci_lo,4),round(ci_hi,4)],
            "macro_auroc":round(auroc,4),"macro_f1":round(f1,4),"accuracy":round(acc,4),
            "training_history":history}
    out_json = os.path.join(OUT_DIR, f"B2_regime2_seed{seed}_results.json")
    with open(out_json,"w") as f: json.dump(result,f,indent=2)
    torch.save(best_state, os.path.join(OUT_DIR, f"B2_regime2_seed{seed}_model.pt"))
    print(f"\n{'='*60}", flush=True)
    print(f"  AUPRC: {auprc:.4f}  [{ci_lo:.4f}, {ci_hi:.4f}]", flush=True)
    print(f"  AUROC: {auroc:.4f}  F1: {f1:.4f}  Acc: {acc:.4f}", flush=True)
    print(f"  Saved: {out_json}", flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--seed",type=int,default=42)
    main(p.parse_args().seed)
