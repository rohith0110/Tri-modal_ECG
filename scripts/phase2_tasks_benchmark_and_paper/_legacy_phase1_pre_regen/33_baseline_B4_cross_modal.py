"""
15_baseline_B4.py — B4/B6 Cross-Modal Verification baseline.
Task: given (signal, text_report) pair → predict y_match (same study vs. mismatched).
Approach: ResNet signal embedding (512d) + TF-IDF text embedding → cosine similarity + LR classifier.
Output: outputs/tables/B4_baseline_results.json
"""
import os, json, random, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score, accuracy_score

B4_JSONL    = "../processed/taskA_verification.jsonl"
SIG_DIR     = "../processed/signals_lead2"
MM_CSV      = "../data/machine_measurements.csv"
MODEL_PT    = "../outputs/model_runs/B1/B1_seed42_model.pt"
OUT_DIR     = "../outputs/tables"
SAMPLE_N    = 4000  # records per split (5.6M total is too large for a baseline demo)
os.makedirs(OUT_DIR, exist_ok=True)

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
    def encode(self,x): return self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1)

def load_sample(jsonl_path, split, n, seed=42):
    rng = random.Random(seed)
    recs = []
    with open(jsonl_path) as f:
        for line in f:
            r = json.loads(line)
            if r["split"] == split:
                recs.append(r)
    rng.shuffle(recs)
    return recs[:n]

def get_signal_emb(study_ids, device, model, batch=256):
    all_embs = []
    model.eval()
    ids = list(study_ids)
    for i in range(0, len(ids), batch):
        batch_ids = ids[i:i+batch]
        sigs = []
        for sid in batch_ids:
            path = os.path.join(SIG_DIR, f"{sid}.npy")
            if os.path.exists(path):
                s = np.load(path).astype(np.float32)
                if np.isnan(s).any(): s = np.zeros(5000, dtype=np.float32)
            else:
                s = np.zeros(5000, dtype=np.float32)
            sigs.append(s)
        sigs = np.array(sigs, dtype=np.float32)
        mu = sigs.mean(1,keepdims=True); sd=sigs.std(1,keepdims=True)+1e-6
        sigs = (sigs-mu)/sd
        Xb = torch.from_numpy(sigs).unsqueeze(1).to(device)
        with torch.no_grad():
            all_embs.append(model.encode(Xb).cpu().numpy())
    return np.concatenate(all_embs)

def load_text_lookup(mm_csv):
    """Build study_id → concatenated report text from machine_measurements.csv."""
    import pandas as pd
    print("  Loading machine_measurements.csv for report text...", flush=True)
    cols_needed = ["study_id"] + [f"report_{i}" for i in range(18)]
    try:
        df = pd.read_csv(mm_csv, usecols=[c for c in cols_needed], low_memory=False)
    except Exception:
        df = pd.read_csv(mm_csv, low_memory=False)
    report_cols = [c for c in df.columns if c.startswith("report_")]
    df["full_report"] = df[report_cols].fillna("").agg(" ".join, axis=1).str.strip()
    # store both int and str keys so lookup works regardless of id type
    lookup = {}
    for sid, txt in zip(df["study_id"], df["full_report"]):
        lookup[str(sid)] = txt
        lookup[int(sid)] = txt
    return lookup

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"B4/B6 Cross-Modal Verification | {device}", flush=True)

    print("Loading B4 sample...", flush=True)
    tr_recs = load_sample(B4_JSONL, "train", SAMPLE_N, seed=42)
    te_recs = load_sample(B4_JSONL, "test",  SAMPLE_N, seed=1)
    print(f"  train={len(tr_recs):,}  test={len(te_recs):,}", flush=True)

    # y_match is stored as string '1'/'0'
    tr_labels = np.array([int(r["y_match"]) for r in tr_recs])
    te_labels = np.array([int(r["y_match"]) for r in te_recs])
    print(f"  Class balance train: {tr_labels.mean():.2f} positive", flush=True)

    # Load text lookup
    text_lookup = load_text_lookup(MM_CSV)

    # ── Signal embeddings ─────────────────────────────────────────────────────
    print("Loading ResNet signal encoder...", flush=True)
    sig_model = ECGResNet1D(3).to(device)
    sig_model.load_state_dict(torch.load(MODEL_PT, map_location=device)); sig_model.eval()

    all_sig_ids = list(set([r["signal_id"] for r in tr_recs+te_recs]))
    print(f"Extracting signal embeddings for {len(all_sig_ids):,} unique signals...", flush=True)
    t0=time.time()
    sig_emb_dict = {}
    for i in range(0, len(all_sig_ids), 256):
        batch_ids = all_sig_ids[i:i+256]
        embs = get_signal_emb(batch_ids, device, sig_model)
        for sid, emb in zip(batch_ids, embs):
            sig_emb_dict[sid] = emb
    print(f"  Signal embeddings done in {time.time()-t0:.1f}s", flush=True)

    # ── TF-IDF text embeddings ────────────────────────────────────────────────
    all_text_ids = list(set([r["text_id"] for r in tr_recs+te_recs]))
    texts = [text_lookup.get(tid, "") for tid in all_text_ids]
    print(f"Fitting TF-IDF on {len(texts):,} unique texts...", flush=True)
    tfidf = TfidfVectorizer(max_features=1000, ngram_range=(1,2), sublinear_tf=True)
    tfidf.fit(texts)
    text_mat = tfidf.transform(texts).toarray().astype(np.float32)
    text_emb_dict = {tid: text_mat[i] for i, tid in enumerate(all_text_ids)}

    # ── Build feature matrix: [signal_emb, text_emb, cosine_sim] → y_match ──
    def build_features(recs):
        feats = []
        for r in recs:
            s_emb = sig_emb_dict.get(r["signal_id"], np.zeros(512, np.float32))
            t_emb = text_emb_dict.get(r["text_id"],  np.zeros(1000, np.float32))
            # Cosine similarity on truncated projections only
            s64 = s_emb[:64] / (np.linalg.norm(s_emb[:64]) + 1e-10)
            t64 = t_emb[:64] / (np.linalg.norm(t_emb[:64]) + 1e-10)
            cos_sim = np.array([float(np.dot(s64, t64))], dtype=np.float32)
            feats.append(np.concatenate([s_emb[:64], t_emb[:64], cos_sim]))
        return np.array(feats, dtype=np.float32)

    print("Building features...", flush=True)
    X_tr = build_features(tr_recs)
    X_te = build_features(te_recs)

    # ── Cosine-similarity-only baseline ──────────────────────────────────────
    cos_tr = np.array([build_features([r])[:,-1] for r in tr_recs]).ravel()
    cos_te = np.array([build_features([r])[:,-1] for r in te_recs]).ravel()
    # map cosine to [0,1]
    cos_probs = (cos_te - cos_te.min()) / (cos_te.max() - cos_te.min() + 1e-10)

    # ── Full feature LR classifier ────────────────────────────────────────────
    print("Training classifier...", flush=True)
    t0=time.time()
    clf = LogisticRegression(max_iter=500, C=0.1, random_state=42)
    clf.fit(X_tr, tr_labels)
    te_probs = clf.predict_proba(X_te)[:,1]
    print(f"  Training done in {time.time()-t0:.1f}s", flush=True)

    def metrics(labels, probs, name):
        preds = (probs>=0.5).astype(int)
        try: auprc=round(float(average_precision_score(labels,probs)),4)
        except: auprc=0.0
        try: auroc=round(float(roc_auc_score(labels,probs)),4)
        except: auroc=0.0
        f1    =round(float(f1_score(labels,preds,zero_division=0)),4)
        acc   =round(float(accuracy_score(labels,preds)),4)
        print(f"  {name}: AUPRC={auprc}  AUROC={auroc}  F1={f1}  Acc={acc}", flush=True)
        return {"auprc":auprc,"auroc":auroc,"f1":f1,"accuracy":acc}

    results = {
        "cosine_similarity_baseline": metrics(te_labels, cos_probs, "Cosine-only"),
        "signal_text_lr_classifier":  metrics(te_labels, te_probs,  "Signal+Text LR"),
        "n_train": len(tr_recs), "n_test": len(te_recs),
        "model": "ResNet512[:64] + TF-IDF1000[:64] + cosine -> LogisticRegression",
        "note": f"Sampled {SAMPLE_N} records per split from 5.6M total for baseline demo",
    }

    out = os.path.join(OUT_DIR, "B4_baseline_results.json")
    with open(out,"w") as f: json.dump(results,f,indent=2)
    print(f"\nSaved: {out}", flush=True)

if __name__ == "__main__":
    main()
