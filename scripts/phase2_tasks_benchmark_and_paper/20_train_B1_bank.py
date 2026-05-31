"""
08_train_bank.py — ResNet-1D training from pre-built signal bank.
Usage: python 08_train_bank.py --seed 42
"""
import os, json, argparse, random, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score
from sklearn.preprocessing import label_binarize

BANK_DIR = "../processed/signal_bank"
OUT_DIR  = "../outputs/model_runs/B1"
EPOCHS, BATCH, LR = 25, 256, 1e-3
HR_NAMES = ["bradycardia", "normal", "tachycardia"]
os.makedirs(OUT_DIR, exist_ok=True)

# ── Architecture ──────────────────────────────────────────────────────────────
class ResBlock1D(nn.Module):
    def __init__(self, a, b, s=1):
        super().__init__()
        self.c1 = nn.Conv1d(a, b, 7, stride=s, padding=3, bias=False)
        self.b1 = nn.BatchNorm1d(b)
        self.c2 = nn.Conv1d(b, b, 7, padding=3, bias=False)
        self.b2 = nn.BatchNorm1d(b)
        self.sk = (nn.Sequential(nn.Conv1d(a, b, 1, stride=s, bias=False), nn.BatchNorm1d(b))
                   if s != 1 or a != b else nn.Identity())
    def forward(self, x):
        return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x))))) + self.sk(x))

class ECGResNet1D(nn.Module):
    def __init__(self, nc=3):
        super().__init__()
        self.stem = nn.Sequential(nn.Conv1d(1,64,15,2,7,bias=False), nn.BatchNorm1d(64), nn.ReLU(), nn.MaxPool1d(3,2,1))
        self.l1   = nn.Sequential(ResBlock1D(64,64),    ResBlock1D(64,64))
        self.l2   = nn.Sequential(ResBlock1D(64,128,2), ResBlock1D(128,128))
        self.l3   = nn.Sequential(ResBlock1D(128,256,2),ResBlock1D(256,256))
        self.l4   = nn.Sequential(ResBlock1D(256,512,2),ResBlock1D(512,512))
        self.head = nn.Linear(512, nc)
    def forward(self, x):
        return self.head(self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1))

# ── Metrics ───────────────────────────────────────────────────────────────────
def bootstrap_auprc(yt, ys, n=1000, seed=0):
    rng = np.random.default_rng(seed); N = len(yt); aucs = []
    for _ in range(n):
        idx = rng.integers(0, N, N)
        try: aucs.append(average_precision_score(yt[idx], ys[idx], average="macro"))
        except: pass
    a = np.array(aucs)
    return float(a.mean()), float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))

# ── Main ──────────────────────────────────────────────────────────────────────
def main(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.backends.cudnn.benchmark = False   # avoid extra auto-tune overhead
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}\nB1 ResNet (bank) | Seed {seed} | {device}\n{'='*60}", flush=True)

    # Load bank
    X_tr = np.load(f"{BANK_DIR}/train_signals.npy"); y_tr = np.load(f"{BANK_DIR}/train_labels.npy")
    X_va = np.load(f"{BANK_DIR}/val_signals.npy");   y_va = np.load(f"{BANK_DIR}/val_labels.npy")
    X_te = np.load(f"{BANK_DIR}/test_signals.npy");  y_te = np.load(f"{BANK_DIR}/test_labels.npy")
    print(f"Bank loaded — train:{len(X_tr):,}  val:{len(X_va):,}  test:{len(X_te):,}", flush=True)

    # Drop any signals that contain NaN (corrupted during bank build)
    for split_name, Xs, ys in [("tr", X_tr, y_tr), ("va", X_va, y_va), ("te", X_te, y_te)]:
        bad = int(np.isnan(Xs).any(axis=1).sum())
        if bad: print(f"  Dropped {bad} NaN rows from {split_name}", flush=True)
    mask_tr = ~np.isnan(X_tr).any(axis=1); X_tr, y_tr = X_tr[mask_tr], y_tr[mask_tr]
    mask_va = ~np.isnan(X_va).any(axis=1); X_va, y_va = X_va[mask_va], y_va[mask_va]
    mask_te = ~np.isnan(X_te).any(axis=1); X_te, y_te = X_te[mask_te], y_te[mask_te]
    print(f"Clean:        train:{len(X_tr):,}  val:{len(X_va):,}  test:{len(X_te):,}", flush=True)
    print(f"Class dist:  {dict(zip(HR_NAMES, [int((y_tr==i).sum()) for i in range(3)]))}", flush=True)

    # Per-sample z-score
    for X in [X_tr, X_va, X_te]:
        mu = X.mean(1, keepdims=True); sd = X.std(1, keepdims=True) + 1e-6
        X[:] = (X - mu) / sd

    def loader(X, y, shuffle=False):
        ds = TensorDataset(torch.from_numpy(X).unsqueeze(1), torch.from_numpy(y))
        return DataLoader(ds, batch_size=BATCH, shuffle=shuffle, num_workers=0, pin_memory=False)

    tr_ldr = loader(X_tr, y_tr, True)
    va_ldr = loader(X_va, y_va)
    te_ldr = loader(X_te, y_te)

    model = ECGResNet1D(3).to(device)
    opt   = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)

    # CUDA warmup — triggers all kernel JIT compilation before the timed loop
    if device.type == "cuda":
        print("CUDA warmup (compiling kernels — takes ~1-5 min first time)...", flush=True)
        t0 = time.time()
        dummy = torch.randn(BATCH, 1, 5000, device=device)
        dummy_y = torch.zeros(BATCH, dtype=torch.long, device=device)
        model.train()
        out = model(dummy); loss = F.cross_entropy(out, dummy_y)
        opt.zero_grad(); loss.backward(); opt.step()
        if device.type == "cuda":
            torch.cuda.synchronize()
        print(f"Warmup done in {time.time()-t0:.1f}s", flush=True)
        model = ECGResNet1D(3).to(device)  # fresh model after warmup
        opt   = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)  # reset seeds

    best_val, best_state, history = float("inf"), None, []
    t_train = time.time()
    print(f"Training {EPOCHS} epochs...", flush=True)

    for ep in range(1, EPOCHS + 1):
        model.train(); losses = []
        for Xb, yb in tr_ldr:
            Xb, yb = Xb.to(device), yb.to(device)
            Xb = Xb * (0.85 + 0.30 * torch.rand(Xb.size(0), 1, 1, device=device))
            loss = F.cross_entropy(model(Xb), yb)
            opt.zero_grad(); loss.backward(); opt.step()
            losses.append(loss.item())
        sched.step()

        model.eval(); vl = []
        with torch.no_grad():
            for Xb, yb in va_ldr:
                vl.append(F.cross_entropy(model(Xb.to(device)), yb.to(device)).item())
        vl_mean = float(np.mean(vl))
        print(f"  Ep{ep:2d}/{EPOCHS}: train={np.mean(losses):.4f}  val={vl_mean:.4f}", flush=True)
        history.append({"epoch": ep, "train_loss": float(np.mean(losses)), "val_loss": vl_mean})
        if vl_mean < best_val:
            best_val = vl_mean
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    print(f"Training done in {time.time()-t_train:.1f}s", flush=True)

    # ── Evaluate on test set ──────────────────────────────────────────────────
    model.load_state_dict(best_state); model.eval()
    logits_all, labels_all = [], []
    with torch.no_grad():
        for Xb, yb in te_ldr:
            logits_all.append(model(Xb.to(device)).cpu().numpy())
            labels_all.append(yb.numpy())
    logits = np.concatenate(logits_all); labels = np.concatenate(labels_all)
    probs  = torch.softmax(torch.from_numpy(logits), -1).numpy()
    preds  = probs.argmax(1)

    labels_bin = label_binarize(labels, classes=[0, 1, 2])
    auprc, ci_lo, ci_hi = bootstrap_auprc(labels_bin, probs)
    auroc = roc_auc_score(labels_bin, probs, average="macro", multi_class="ovr")
    f1    = f1_score(labels, preds, average="macro", zero_division=0)
    acc   = float((labels == preds).mean())
    npc   = {c: int((labels == i).sum()) for i, c in enumerate(HR_NAMES)}

    result = {
        "task": "B1_hr_label", "seed": seed, "model": "ECGResNet1D_1lead",
        "n_test_ecg": int(len(labels)), "n_test_subjects": "500 (bank subset)",
        "n_per_class": npc, "training_subset": "2500 train / 500 val / 500 test",
        "macro_auprc": round(auprc, 4), "auprc_ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "macro_auroc": round(auroc, 4), "macro_f1": round(f1, 4), "accuracy": round(acc, 4),
        "training_history": history, "epochs": EPOCHS, "batch_size": BATCH,
    }
    out = os.path.join(OUT_DIR, f"B1_seed{seed}_results.json")
    with open(out, "w") as f: json.dump(result, f, indent=2)
    # Save model weights for downstream tasks (B2 evaluation, fusion)
    torch.save(best_state, os.path.join(OUT_DIR, f"B1_seed{seed}_model.pt"))

    print(f"\n{'='*60}", flush=True)
    print(f"  AUPRC: {auprc:.4f}  [{ci_lo:.4f}, {ci_hi:.4f}]", flush=True)
    print(f"  AUROC: {auroc:.4f}  F1: {f1:.4f}  Acc: {acc:.4f}", flush=True)
    print(f"  Per class: {npc}", flush=True)
    print(f"  Saved: {out}", flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    main(p.parse_args().seed)
