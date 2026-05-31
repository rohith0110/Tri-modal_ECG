"""
08_train_baselines_fast.py — Windows-compatible ResNet training (num_workers=0)
Trains on a 100K subset per epoch for fast iteration; full dataset sampled each epoch.
Usage: python 08_train_baselines_fast.py --seed 42
"""

import os, json, argparse, random
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score
from sklearn.preprocessing import label_binarize
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
B1_PATH     = "../processed/taskB1_measurement_blind.jsonl"
OUT_DIR     = "../outputs/model_runs/B1"
EPOCHS      = 20
BATCH_SIZE  = 256
LR          = 1e-3
TRAIN_LIMIT = 80000   # samples per epoch (fast subset; full=640K)
os.makedirs(OUT_DIR, exist_ok=True)

# ── Architecture ──────────────────────────────────────────────────────────────

class ResBlock1D(nn.Module):
    def __init__(self, ch_in, ch_out, stride=1):
        super().__init__()
        self.c1 = nn.Conv1d(ch_in,  ch_out, 7, stride=stride, padding=3, bias=False)
        self.b1 = nn.BatchNorm1d(ch_out)
        self.c2 = nn.Conv1d(ch_out, ch_out, 7, padding=3, bias=False)
        self.b2 = nn.BatchNorm1d(ch_out)
        self.skip = (nn.Sequential(nn.Conv1d(ch_in, ch_out, 1, stride=stride, bias=False),
                                   nn.BatchNorm1d(ch_out))
                     if stride != 1 or ch_in != ch_out else nn.Identity())
    def forward(self, x):
        return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x))))) + self.skip(x))

class ECGResNet1D(nn.Module):
    def __init__(self, n_classes=3):
        super().__init__()
        self.stem   = nn.Sequential(nn.Conv1d(1,64,15,2,7,bias=False), nn.BatchNorm1d(64), nn.ReLU(), nn.MaxPool1d(3,2,1))
        self.layer1 = nn.Sequential(ResBlock1D(64,64),   ResBlock1D(64,64))
        self.layer2 = nn.Sequential(ResBlock1D(64,128,2),ResBlock1D(128,128))
        self.layer3 = nn.Sequential(ResBlock1D(128,256,2),ResBlock1D(256,256))
        self.layer4 = nn.Sequential(ResBlock1D(256,512,2),ResBlock1D(512,512))
        self.head   = nn.Linear(512, n_classes)
    def forward(self, x):
        x = self.stem(x)
        x = self.layer4(self.layer3(self.layer2(self.layer1(x))))
        return self.head(x.mean(-1))

# ── Dataset ───────────────────────────────────────────────────────────────────

HR_MAP  = {"bradycardia": 0, "normal": 1, "tachycardia": 2}
HR_NAMES = ["bradycardia", "normal", "tachycardia"]

class B1Dataset(Dataset):
    def __init__(self, records, augment=False):
        self.records = records
        self.augment = augment
    def __len__(self): return len(self.records)
    def __getitem__(self, i):
        rec = self.records[i]
        sig = np.load(rec["signal_path"]).astype(np.float32)
        if self.augment:
            sig *= np.random.uniform(0.85, 1.15)
            sig += np.random.normal(0, 0.005, sig.shape).astype(np.float32)
        return torch.from_numpy(sig).unsqueeze(0), HR_MAP[rec["hr_label"]]

def load_split(path, split):
    recs = []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            if r["split"] == split:
                recs.append(r)
    return recs

# ── Bootstrap CI ─────────────────────────────────────────────────────────────

def bootstrap_auprc(y_true_bin, y_score, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    N   = len(y_true_bin)
    aucs = []
    for _ in range(n):
        idx = rng.integers(0, N, N)
        try: aucs.append(average_precision_score(y_true_bin[idx], y_score[idx], average="macro"))
        except: pass
    return float(np.mean(aucs)), float(np.percentile(aucs,2.5)), float(np.percentile(aucs,97.5))

# ── Main ──────────────────────────────────────────────────────────────────────

def main(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}\nB1 ResNet | Seed {seed} | {device}\n{'='*60}")

    print("Loading splits from JSONL (this takes ~1 min)...")
    train_all = load_split(B1_PATH, "train")
    val_recs  = load_split(B1_PATH, "val")
    test_recs = load_split(B1_PATH, "test")
    print(f"  train={len(train_all):,}  val={len(val_recs):,}  test={len(test_recs):,}")

    val_ds  = B1Dataset(val_recs,  augment=False)
    test_ds = B1Dataset(test_recs, augment=False)
    val_loader  = DataLoader(val_ds,  batch_size=512, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=512, shuffle=False, num_workers=0)

    model = ECGResNet1D(n_classes=3).to(device)
    opt   = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)

    best_val, best_state, history = float("inf"), None, []

    for epoch in range(1, EPOCHS+1):
        # Sample a subset each epoch (faster I/O than full 640K)
        epoch_recs = random.sample(train_all, min(TRAIN_LIMIT, len(train_all)))
        train_ds   = B1Dataset(epoch_recs, augment=True)
        train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)

        model.train()
        losses = []
        for sig, lbl in tqdm(train_loader, desc=f"Ep{epoch:2d}", leave=False):
            sig, lbl = sig.to(device), lbl.to(device)
            loss = F.cross_entropy(model(sig), lbl)
            opt.zero_grad(); loss.backward(); opt.step()
            losses.append(loss.item())
        sched.step()

        model.eval()
        val_losses = []
        with torch.no_grad():
            for sig, lbl in val_loader:
                val_losses.append(F.cross_entropy(model(sig.to(device)), lbl.to(device)).item())
        val_loss = float(np.mean(val_losses))
        print(f"  Ep{epoch:2d}: train={np.mean(losses):.4f}  val={val_loss:.4f}")
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "val_loss": val_loss})

        if val_loss < best_val:
            best_val   = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    # ── Test evaluation ───────────────────────────────────────────────────────
    model.load_state_dict(best_state)
    model.eval()
    logits_all, labels_all = [], []
    with torch.no_grad():
        for sig, lbl in tqdm(test_loader, desc="Testing"):
            logits_all.append(model(sig.to(device)).cpu().numpy())
            labels_all.append(lbl.numpy())

    logits = np.concatenate(logits_all)
    labels = np.concatenate(labels_all)
    probs  = torch.softmax(torch.from_numpy(logits), -1).numpy()
    preds  = probs.argmax(axis=1)

    labels_bin = label_binarize(labels, classes=[0,1,2])
    auprc, ci_lo, ci_hi = bootstrap_auprc(labels_bin, probs)
    auroc = roc_auc_score(labels_bin, probs, average="macro", multi_class="ovr")
    f1    = f1_score(labels, preds, average="macro", zero_division=0)
    acc   = float((labels == preds).mean())

    n_per_class = {c: int((labels==i).sum()) for i,c in enumerate(HR_NAMES)}

    result = {
        "task": "B1_hr_label", "seed": seed, "model": "ECGResNet1D_1lead",
        "n_test_ecg": int(len(labels)), "n_test_subjects": "see splits_subject_level.parquet",
        "n_per_class": n_per_class,
        "macro_auprc": round(auprc,4), "auprc_ci_95": [round(ci_lo,4), round(ci_hi,4)],
        "macro_auroc": round(auroc,4), "macro_f1": round(f1,4), "accuracy": round(acc,4),
        "training_history": history, "train_subset_per_epoch": TRAIN_LIMIT,
        "epochs": EPOCHS, "batch_size": BATCH_SIZE,
    }

    out_path = os.path.join(OUT_DIR, f"B1_seed{seed}_results.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n{'='*60}")
    print(f"  AUPRC: {auprc:.4f}  [{ci_lo:.4f}, {ci_hi:.4f}]")
    print(f"  AUROC: {auroc:.4f}  F1: {f1:.4f}  Acc: {acc:.4f}")
    print(f"  Saved: {out_path}")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(args.seed)
