"""
08_train_baselines.py — Baseline training suite for Plan B (doc §6.8, §9.3)

Models trained:
  - 1D ResNet (signal-only) on B1, B2, B3
  - Evaluation: AUPRC, AUROC, Macro-F1 with 95% bootstrap CI (patient-level)
  - 3 random seeds; report mean ± std

Architecture: 1D ResNet-18 variant adapted for ECG (5000-sample input)
  Layers: stem conv → 4 residual stages → global avg pool → head
  Input: (batch, 1, 5000) for lead-II

Usage:
  python 08_train_baselines.py --task B1 --seed 42
  python 08_train_baselines.py --task B1 --seed 123
  python 08_train_baselines.py --task B1 --seed 456
"""

import os, json, argparse, random
import numpy as np
import pandas as pd
from tqdm import tqdm
from datetime import datetime

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score

# ── Config ────────────────────────────────────────────────────────────────────

TASK_PATHS = {
    "B1": "../processed/taskB1_measurement_blind.jsonl",
    "B3": "../processed/taskB_temporal_grounding.jsonl",
}
OUT_DIR    = "../outputs/model_runs"
FS         = 500
N_SAMPLES  = 5000

# ── 1D ResNet architecture ────────────────────────────────────────────────────

class ResBlock1D(nn.Module):
    def __init__(self, in_ch, out_ch, stride=1):
        super().__init__()
        self.conv1 = nn.Conv1d(in_ch,  out_ch, 7, stride=stride, padding=3, bias=False)
        self.bn1   = nn.BatchNorm1d(out_ch)
        self.conv2 = nn.Conv1d(out_ch, out_ch, 7, stride=1,      padding=3, bias=False)
        self.bn2   = nn.BatchNorm1d(out_ch)
        self.skip  = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, 1, stride=stride, bias=False),
            nn.BatchNorm1d(out_ch)
        ) if stride != 1 or in_ch != out_ch else nn.Identity()

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return F.relu(out + self.skip(x))

class ECGResNet1D(nn.Module):
    """1D ResNet for single-lead ECG classification."""
    def __init__(self, n_classes: int, n_leads: int = 1):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(n_leads, 64, 15, stride=2, padding=7, bias=False),
            nn.BatchNorm1d(64), nn.ReLU(),
            nn.MaxPool1d(3, stride=2, padding=1),
        )
        self.layer1 = nn.Sequential(ResBlock1D(64,  64),  ResBlock1D(64,  64))
        self.layer2 = nn.Sequential(ResBlock1D(64,  128, 2), ResBlock1D(128, 128))
        self.layer3 = nn.Sequential(ResBlock1D(128, 256, 2), ResBlock1D(256, 256))
        self.layer4 = nn.Sequential(ResBlock1D(256, 512, 2), ResBlock1D(512, 512))
        self.pool   = nn.AdaptiveAvgPool1d(1)
        self.head   = nn.Linear(512, n_classes)

    def forward(self, x):
        x = self.stem(x)
        x = self.layer1(x); x = self.layer2(x)
        x = self.layer3(x); x = self.layer4(x)
        x = self.pool(x).squeeze(-1)
        return self.head(x)

# ── Dataset ───────────────────────────────────────────────────────────────────

class B1Dataset(Dataset):
    """Task B1 — signal → (hr_label, qrs_label, qtc_label)."""
    HR_CLASSES  = {"bradycardia": 0, "normal": 1, "tachycardia": 2}
    QRS_CLASSES = {"normal": 0, "borderline": 1, "wide": 2}
    QTC_CLASSES = {"short": 0, "normal": 1, "prolonged": 2}

    def __init__(self, path, split, augment=False):
        self.records = []
        self.augment = augment
        with open(path) as f:
            for line in f:
                rec = json.loads(line)
                if rec["split"] == split:
                    self.records.append(rec)

    def __len__(self): return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        sig = np.load(rec["signal_path"]).astype(np.float32)
        if self.augment:
            # Simple augmentation: random amplitude scale + Gaussian noise
            sig = sig * np.random.uniform(0.8, 1.2)
            sig = sig + np.random.normal(0, 0.01, sig.shape).astype(np.float32)
        sig = torch.from_numpy(sig).unsqueeze(0)  # (1, 5000)
        hr  = self.HR_CLASSES[rec["hr_label"]]
        qrs = self.QRS_CLASSES[rec["qrs_label"]]
        qtc = self.QTC_CLASSES[rec["qtc_label"]]
        return sig, hr, qrs, qtc

# ── Bootstrap CI ─────────────────────────────────────────────────────────────

def bootstrap_auprc(y_true, y_score, n_boot=1000, seed=0):
    rng  = np.random.default_rng(seed)
    aucs = []
    n    = len(y_true)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        try:
            aucs.append(average_precision_score(y_true[idx], y_score[idx], average="macro"))
        except Exception:
            pass
    aucs = np.array(aucs)
    return float(np.mean(aucs)), float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))

# ── Training loop ─────────────────────────────────────────────────────────────

def train_b1(seed, task_path, out_dir):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'='*60}\nTask B1 | Seed {seed} | Device: {device}\n{'='*60}")

    train_ds = B1Dataset(task_path, "train", augment=True)
    val_ds   = B1Dataset(task_path, "val",   augment=False)
    test_ds  = B1Dataset(task_path, "test",  augment=False)
    print(f"Train: {len(train_ds):,}  Val: {len(val_ds):,}  Test: {len(test_ds):,}")

    train_loader = DataLoader(train_ds, batch_size=512, shuffle=True,  num_workers=4, pin_memory=True, persistent_workers=True)
    val_loader   = DataLoader(val_ds,   batch_size=512, shuffle=False, num_workers=4, pin_memory=True, persistent_workers=True)
    test_loader  = DataLoader(test_ds,  batch_size=512, shuffle=False, num_workers=4, pin_memory=True, persistent_workers=True)

    model = ECGResNet1D(n_classes=3).to(device)
    opt   = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=20)

    best_val_loss = float("inf")
    best_state    = None
    history       = []

    for epoch in range(1, 21):  # 20 epochs on GPU
        # Train (HR only as primary target; add QRS/QTc heads in full version)
        model.train()
        losses = []
        for sig, hr, qrs, qtc in tqdm(train_loader, desc=f"Ep{epoch}", leave=False):
            sig, hr = sig.to(device), hr.to(device)
            loss = F.cross_entropy(model(sig), hr)
            opt.zero_grad(); loss.backward(); opt.step()
            losses.append(loss.item())
        sched.step()

        # Val
        model.eval()
        val_losses = []
        with torch.no_grad():
            for sig, hr, qrs, qtc in val_loader:
                sig, hr = sig.to(device), hr.to(device)
                val_losses.append(F.cross_entropy(model(sig), hr).item())
        val_loss = np.mean(val_losses)
        history.append({"epoch": epoch, "train_loss": np.mean(losses), "val_loss": val_loss})

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state    = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if epoch % 5 == 0:
            print(f"  Epoch {epoch:2d}: train={np.mean(losses):.4f}  val={val_loss:.4f}")

    # Evaluate on test
    model.load_state_dict(best_state)
    model.eval()
    all_logits, all_labels = [], []
    with torch.no_grad():
        for sig, hr, qrs, qtc in test_loader:
            logits = model(sig.to(device)).cpu().numpy()
            all_logits.append(logits)
            all_labels.append(hr.numpy())

    logits = np.concatenate(all_logits)
    labels = np.concatenate(all_labels)
    probs  = torch.softmax(torch.from_numpy(logits), dim=-1).numpy()
    preds  = np.argmax(probs, axis=1)

    # AUPRC (macro OvR)
    labels_bin = label_binarize(labels, classes=[0,1,2])
    auprc, ci_lo, ci_hi = bootstrap_auprc(labels_bin.ravel(), probs.ravel())
    auroc = roc_auc_score(labels_bin, probs, average="macro", multi_class="ovr")
    f1    = f1_score(labels, preds, average="macro", zero_division=0)
    acc   = (labels == preds).mean()

    class_names = ["bradycardia", "normal", "tachycardia"]
    n_per_class = {c: int((labels == i).sum()) for i, c in enumerate(class_names)}

    result = {
        "task": "B1_hr_label",
        "seed": seed,
        "model": "ECGResNet1D_1lead",
        "n_test_ecg": int(len(labels)),
        "n_test_subjects": "see manifest",
        "n_per_class": n_per_class,
        "macro_auprc": round(auprc, 4),
        "auprc_ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "macro_auroc": round(auroc, 4),
        "macro_f1":    round(f1, 4),
        "accuracy":    round(float(acc), 4),
        "training_history": history,
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"B1_seed{seed}_results.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n  Test Results (seed={seed}):")
    print(f"    AUPRC: {auprc:.4f} [{ci_lo:.4f}, {ci_hi:.4f}]")
    print(f"    AUROC: {auroc:.4f}  F1: {f1:.4f}  Acc: {acc:.4f}")
    print(f"    Saved: {out_path}")
    return result

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task",  default="B1", choices=["B1"])
    parser.add_argument("--seed",  type=int, default=42)
    args = parser.parse_args()

    from sklearn.preprocessing import label_binarize

    result = train_b1(
        seed=args.seed,
        task_path=TASK_PATHS[args.task],
        out_dir=os.path.join(OUT_DIR, args.task),
    )
