"""
17_baseline_B6.py — B6 Difficulty-Stratified Cross-Modal Verification.
Task: Given (signal, text) pair, predict y_match=1 (same study) vs y_match=0 (hard negative).
Six levels of negatives, matched on increasing physiological bins:
  Level 0: random subject
  Level 1: matched on HR bin
  Level 2: matched on HR + QRS bin
  Level 3: matched on HR + QRS + axis bin
  Level 4: same patient, different study
  Level 5: nearest signal-embedding neighbor (hardest structural negative)
Output: outputs/tables/B6_verification_curve.json
"""
import os, json, random, time
import numpy as np
import pandas as pd
import torch, torch.nn as nn, torch.nn.functional as F
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score, average_precision_score

MM_CSV    = "../data/machine_measurements.csv"
B1_JSONL  = "../processed/taskB1_measurement_blind.jsonl"
SIG_DIR   = "../processed/signals_lead2"
MODEL_PT  = "../outputs/model_runs/B1/B1_seed42_model.pt"
OUT_DIR   = "../outputs/tables"
SAMPLE_N  = 2000   # anchors per level from test split
SEED      = 42
os.makedirs(OUT_DIR, exist_ok=True)

# ── ResNet (same arch as B1) ───────────────────────────────────────────────────
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
    def encode(self, x): return self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1)

def load_signal(study_id, length=5000):
    path = os.path.join(SIG_DIR, f"{study_id}.npy")
    if not os.path.exists(path):
        return np.zeros(length, dtype=np.float32)
    s = np.load(path).astype(np.float32)
    if np.isnan(s).any():
        return np.zeros(length, dtype=np.float32)
    return s

def get_signal_embs(study_ids, model, device, batch=256):
    model.eval()
    embs = []
    ids = list(study_ids)
    for i in range(0, len(ids), batch):
        b_ids = ids[i:i+batch]
        sigs = np.array([load_signal(sid) for sid in b_ids], dtype=np.float32)
        mu = sigs.mean(1, keepdims=True); sd = sigs.std(1, keepdims=True) + 1e-6
        sigs = (sigs - mu) / sd
        Xb = torch.from_numpy(sigs).unsqueeze(1).to(device)
        with torch.no_grad():
            embs.append(model.encode(Xb).cpu().numpy())
    return np.concatenate(embs, axis=0)

def bin_hr(hr_bpm):
    if hr_bpm < 60:   return "brady"
    if hr_bpm > 100:  return "tachy"
    return "normal"

def bin_qrs(qrs_ms):
    if qrs_ms < 100:  return "narrow"
    if qrs_ms >= 120: return "wide"
    return "borderline"

def bin_axis(axis_deg):
    if axis_deg < -30:  return "LAD"
    if axis_deg > 90:   return "RAD"
    return "normal"

def mrr_score(labels, scores):
    # Mean reciprocal rank: for each positive, rank among negatives
    order = np.argsort(-scores)
    pos_idx = np.where(labels[order] == 1)[0]
    if len(pos_idx) == 0:
        return 0.0
    return float(np.mean(1.0 / (pos_idx + 1)))

def main():
    rng = random.Random(SEED)
    np.random.seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"B6 Difficulty-Stratified Verification | {device}", flush=True)

    # ── Load machine measurements for binning ─────────────────────────────────
    print("Loading machine measurements...", flush=True)
    mm = pd.read_csv(MM_CSV, usecols=["study_id","rr_interval","qrs_onset","qrs_end","qrs_axis"]
                     + [f"report_{i}" for i in range(18)], low_memory=False)
    # Compute derived measurements
    mm["hr_bpm"]   = 60000.0 / mm["rr_interval"].replace(0, np.nan)
    mm["qrs_ms"]   = mm["qrs_end"] - mm["qrs_onset"]
    # Filter plausible values
    mm = mm[(mm["hr_bpm"].between(20, 300)) & (mm["qrs_ms"].between(40, 300)) &
            (mm["qrs_axis"].between(-180, 360))].copy()
    mm["hr_bin"]   = mm["hr_bpm"].apply(bin_hr)
    mm["qrs_bin"]  = mm["qrs_ms"].apply(bin_qrs)
    mm["axis_bin"] = mm["qrs_axis"].apply(bin_axis)
    mm["full_text"] = mm[[f"report_{i}" for i in range(18)]].fillna("").agg(" ".join, axis=1).str.strip()
    mm_dict = mm.set_index("study_id").to_dict("index")
    print(f"  MM records: {len(mm):,}", flush=True)

    # ── Load test records from B1 (has study_id + subject_id) ─────────────────
    print("Loading B1 test records...", flush=True)
    test_recs = []
    with open(B1_JSONL) as f:
        for line in f:
            r = json.loads(line)
            if r["split"] == "test" and r["study_id"] in mm_dict:
                test_recs.append(r)
    rng.shuffle(test_recs)
    print(f"  Test records available: {len(test_recs):,}", flush=True)

    # Build lookup structures for hard-negative construction
    by_hr   = {}   # hr_bin -> [study_id, ...]
    by_hr_qrs = {} # (hr_bin, qrs_bin) -> [study_id, ...]
    by_hr_qrs_ax = {} # (hr_bin, qrs_bin, axis_bin) -> [study_id, ...]
    by_subject = {} # subject_id -> [study_id, ...]
    all_test_ids = [r["study_id"] for r in test_recs]

    for r in test_recs:
        sid = r["study_id"]; subj = r["subject_id"]
        m = mm_dict.get(sid, {})
        if not m: continue
        h = m["hr_bin"]; q = m["qrs_bin"]; a = m["axis_bin"]
        by_hr.setdefault(h, []).append(sid)
        by_hr_qrs.setdefault((h, q), []).append(sid)
        by_hr_qrs_ax.setdefault((h, q, a), []).append(sid)
        by_subject.setdefault(subj, []).append(sid)

    # ── Load ResNet signal encoder ─────────────────────────────────────────────
    print("Loading ResNet signal encoder...", flush=True)
    model = ECGResNet1D(3).to(device)
    model.load_state_dict(torch.load(MODEL_PT, map_location=device))
    model.eval()

    # ── Sample anchors and build pairs for each level ─────────────────────────
    anchors = test_recs[:SAMPLE_N]
    anchor_ids = [r["study_id"] for r in anchors]
    anchor_subj = {r["study_id"]: r["subject_id"] for r in anchors}
    all_ids_set = set(all_test_ids)

    def pick_neg(anchor_sid, pool, exclude_subj=None):
        """Pick a random negative from pool (different study, optionally different subject)."""
        candidates = [s for s in pool if s != anchor_sid]
        if exclude_subj is not None:
            candidates = [s for s in candidates if by_subject.get(anchor_subj.get(anchor_sid), []) and
                          s not in by_subject.get(anchor_subj.get(anchor_sid), [])]
        if not candidates:
            # fallback: any different study
            candidates = [s for s in all_test_ids if s != anchor_sid]
        return rng.choice(candidates)

    def build_pairs(level):
        """Build (anchor_id, neg_id, label) pairs for a given level."""
        pairs = []
        for r in anchors:
            sid = r["study_id"]; subj = r["subject_id"]
            m = mm_dict.get(sid, {})
            if not m: continue
            h = m["hr_bin"]; q = m["qrs_bin"]; a = m["axis_bin"]

            if level == 0:
                pool = all_test_ids
            elif level == 1:
                pool = by_hr.get(h, all_test_ids)
            elif level == 2:
                pool = by_hr_qrs.get((h, q), by_hr.get(h, all_test_ids))
            elif level == 3:
                pool = by_hr_qrs_ax.get((h, q, a), by_hr_qrs.get((h, q), all_test_ids))
            elif level == 4:
                # Same patient, different study
                same_subj = [s for s in by_subject.get(subj, []) if s != sid]
                if same_subj:
                    neg_sid = rng.choice(same_subj)
                    pairs.append((sid, neg_sid))
                    continue
                else:
                    pool = all_test_ids  # fallback
            elif level == 5:
                # Nearest embedding (constructed after embedding step)
                pool = all_test_ids

            neg_sid = pick_neg(sid, pool)
            pairs.append((sid, neg_sid))
        return pairs

    # Pre-compute pairs for levels 0-4
    level_pairs = {}
    for lvl in range(5):
        level_pairs[lvl] = build_pairs(lvl)
        print(f"  Level {lvl}: {len(level_pairs[lvl])} pairs", flush=True)

    # ── Compute signal embeddings for all relevant studies ─────────────────────
    needed_ids = set(anchor_ids)
    for lvl in range(5):
        for a, b in level_pairs[lvl]:
            needed_ids.add(a); needed_ids.add(b)
    needed_ids = list(needed_ids)

    print(f"Computing signal embeddings for {len(needed_ids):,} studies...", flush=True)
    t0 = time.time()
    emb_arr = get_signal_embs(needed_ids, model, device)
    emb_dict = {sid: emb_arr[i] for i, sid in enumerate(needed_ids)}
    print(f"  Done in {time.time()-t0:.1f}s", flush=True)

    # Level 5: nearest embedding neighbor (same HR+QRS+axis bin, closest in embedding space)
    print("Building Level 5 (nearest-embedding) pairs...", flush=True)
    l5_pairs = []
    for r in anchors:
        sid = r["study_id"]
        m = mm_dict.get(sid, {})
        if not m: continue
        h = m["hr_bin"]; q = m["qrs_bin"]; a_bin = m["axis_bin"]
        pool_ids = by_hr_qrs_ax.get((h, q, a_bin), by_hr_qrs.get((h, q), all_test_ids))
        # Find nearest neighbor in embedding space (excluding self)
        anchor_emb = emb_dict.get(sid)
        if anchor_emb is None:
            l5_pairs.append((sid, rng.choice(all_test_ids)))
            continue
        pool_ids_ok = [s for s in pool_ids if s != sid and s in emb_dict]
        if not pool_ids_ok:
            l5_pairs.append((sid, rng.choice(all_test_ids)))
            continue
        pool_embs = np.array([emb_dict[s] for s in pool_ids_ok])
        # Cosine distances
        ae_n = anchor_emb / (np.linalg.norm(anchor_emb) + 1e-10)
        pe_n = pool_embs / (np.linalg.norm(pool_embs, axis=1, keepdims=True) + 1e-10)
        sims = pe_n @ ae_n
        nearest = pool_ids_ok[int(np.argmax(sims))]
        l5_pairs.append((sid, nearest))
    level_pairs[5] = l5_pairs
    print(f"  Level 5: {len(l5_pairs)} pairs", flush=True)

    # ── TF-IDF text embeddings ─────────────────────────────────────────────────
    all_pair_ids = set(anchor_ids)
    for lvl in range(6):
        for a, b in level_pairs[lvl]:
            all_pair_ids.add(a); all_pair_ids.add(b)
    all_pair_ids = list(all_pair_ids)

    texts = [mm_dict[sid]["full_text"] if sid in mm_dict else "" for sid in all_pair_ids]
    print(f"Fitting TF-IDF on {len(texts)} texts...", flush=True)
    tfidf = TfidfVectorizer(max_features=2000, ngram_range=(1, 2), sublinear_tf=True)
    tfidf.fit(texts)
    tmat = tfidf.transform(texts).toarray().astype(np.float32)
    text_emb = {sid: tmat[i] for i, sid in enumerate(all_pair_ids)}

    # ── Train a classifier on Level-0 pairs (most general) ────────────────────
    print("Training classifier on Level-0 pairs...", flush=True)
    def pair_features(pairs, label):
        feats = []; lbls = []
        for (pos_id, neg_id) in pairs:
            for (sig_id, txt_id, y) in [(pos_id, pos_id, 1), (neg_id, pos_id, 0)]:
                se = emb_dict.get(sig_id, np.zeros(512, np.float32))[:64]
                te = text_emb.get(txt_id, np.zeros(2000, np.float32))[:64]
                se_n = se / (np.linalg.norm(se) + 1e-10)
                te_n = te / (np.linalg.norm(te) + 1e-10)
                cos = np.array([float(np.dot(se_n, te_n))], dtype=np.float32)
                feats.append(np.concatenate([se, te, cos]))
                lbls.append(y)
        return np.array(feats, dtype=np.float32), np.array(lbls)

    X_tr, y_tr = pair_features(level_pairs[0], 1)
    clf = LogisticRegression(max_iter=500, C=0.1, random_state=SEED)
    clf.fit(X_tr, y_tr)
    print("  Classifier trained.", flush=True)

    # ── Evaluate at each level ─────────────────────────────────────────────────
    results = {"levels": {}, "n_anchors": len(anchors)}
    level_names = {
        0: "Random negative",
        1: "Matched HR bin",
        2: "Matched HR+QRS bins",
        3: "Matched HR+QRS+axis bins",
        4: "Same patient, different study",
        5: "Nearest signal embedding",
    }

    for lvl in range(6):
        pairs = level_pairs[lvl]
        X_te, y_te = pair_features(pairs, 1)
        probs = clf.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)
        try: auroc = round(float(roc_auc_score(y_te, probs)), 4)
        except: auroc = 0.5
        try: auprc = round(float(average_precision_score(y_te, probs)), 4)
        except: auprc = 0.0
        acc   = round(float(accuracy_score(y_te, preds)), 4)
        mrr   = round(float(mrr_score(y_te, probs)), 4)
        n_pos = int(y_te.sum())
        print(f"  Level {lvl} ({level_names[lvl]}): AUROC={auroc}  Acc={acc}  MRR={mrr}  n_pos={n_pos}", flush=True)
        results["levels"][lvl] = {
            "name": level_names[lvl],
            "n_pairs": len(pairs),
            "n_positive": n_pos,
            "auroc": auroc,
            "auprc": auprc,
            "accuracy": acc,
            "mrr": mrr,
        }

    results["model"] = "ResNet512[:64] + TF-IDF2000[:64] + cosine → LR trained on Level-0 pairs"
    results["note"] = f"Levels 0-5 hard-negative construction; {SAMPLE_N} anchors from test split"

    out = os.path.join(OUT_DIR, "B6_verification_curve.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}", flush=True)

if __name__ == "__main__":
    main()
