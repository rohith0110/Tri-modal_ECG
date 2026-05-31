"""
14_baseline_B5.py — B5 Contradiction Detection baselines (unimodal + multimodal).
  Model A: Text-only  — TF-IDF + Logistic Regression on corrupted_report_text
  Model B: Signal+Text (multimodal) — ResNet signal embedding + TF-IDF → MLP
Input policy allows: report_text + signal_lead2 (machine_measurements FORBIDDEN)
Output: outputs/tables/B5_baseline_results.json
"""
import os, json, time
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score, accuracy_score
from sklearn.preprocessing import label_binarize

B5_JSONL  = "../processed/taskB5_contradiction_detection.jsonl"
SIG_DIR   = "../processed/signals_lead2"
MODEL_PT  = "../outputs/model_runs/B1/B1_seed42_model.pt"
OUT_DIR   = "../outputs/tables"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Signal encoder (load trained B1 ResNet, use as frozen feature extractor) ─
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
    def encode(self,x): return self.l4(self.l3(self.l2(self.l1(self.stem(x))))).mean(-1)  # 512-d

def load_records(jsonl_path):
    splits = {"train":[], "val":[], "test":[]}
    with open(jsonl_path) as f:
        for line in f:
            r = json.loads(line)
            splits[r["split"]].append(r)
    return splits

def get_texts_labels(recs):
    texts  = [r["corrupted_report_text"] or "" for r in recs]
    labels = np.array([1 if r["is_corrupted"] else 0 for r in recs], dtype=np.int64)
    return texts, labels

def load_signals(recs, device, model, batch=256):
    """Extract 512-d signal embeddings. Returns (N,512) float32 array."""
    embs = []
    model.eval()
    for i in range(0, len(recs), batch):
        batch_recs = recs[i:i+batch]
        sigs = []
        for r in batch_recs:
            path = os.path.join(SIG_DIR, f"{r['study_id']}.npy")
            if os.path.exists(path):
                s = np.load(path).astype(np.float32)
                if np.isnan(s).any(): s = np.zeros(5000, dtype=np.float32)
            else:
                s = np.zeros(5000, dtype=np.float32)
            sigs.append(s)
        sigs = np.array(sigs, dtype=np.float32)
        mu = sigs.mean(1,keepdims=True); sd = sigs.std(1,keepdims=True)+1e-6
        sigs = (sigs-mu)/sd
        Xb = torch.from_numpy(sigs).unsqueeze(1).to(device)
        with torch.no_grad():
            embs.append(model.encode(Xb).cpu().numpy())
        if (i//batch) % 5 == 0:
            print(f"    signal embeddings {i+len(batch_recs)}/{len(recs)}", flush=True)
    return np.concatenate(embs)

def report_metrics(labels, probs, name):
    preds = (probs >= 0.5).astype(int)
    auprc = average_precision_score(labels, probs)
    auroc = roc_auc_score(labels, probs)
    f1    = f1_score(labels, preds, zero_division=0)
    acc   = accuracy_score(labels, preds)
    print(f"  {name}: AUPRC={auprc:.4f}  AUROC={auroc:.4f}  F1={f1:.4f}  Acc={acc:.4f}", flush=True)
    return {"auprc":round(auprc,4),"auroc":round(auroc,4),"f1":round(f1,4),"accuracy":round(acc,4)}

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"B5 Contradiction Detection | {device}", flush=True)

    print("Loading B5 records...", flush=True)
    splits = load_records(B5_JSONL)
    tr_recs = splits["train"]; va_recs = splits["val"]; te_recs = splits["test"]
    print(f"  train={len(tr_recs):,}  val={len(va_recs):,}  test={len(te_recs):,}", flush=True)

    tr_texts, tr_labels = get_texts_labels(tr_recs)
    va_texts, va_labels = get_texts_labels(va_recs)
    te_texts, te_labels = get_texts_labels(te_recs)

    results = {}

    # ── Model A: Text-only TF-IDF + Logistic Regression ──────────────────────
    print("\n[A] Text-only baseline (TF-IDF + LogReg)...", flush=True)
    t0 = time.time()
    tfidf = TfidfVectorizer(max_features=5000, ngram_range=(1,2), sublinear_tf=True)
    X_tr_tfidf = tfidf.fit_transform(tr_texts)
    X_te_tfidf = tfidf.transform(te_texts)
    clf_text = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
    clf_text.fit(X_tr_tfidf, tr_labels)
    te_probs_text = clf_text.predict_proba(X_te_tfidf)[:,1]
    print(f"  Trained in {time.time()-t0:.1f}s", flush=True)
    results["text_only"] = report_metrics(te_labels, te_probs_text, "Text-only")
    results["text_only"]["n_test"] = len(te_recs)
    results["text_only"]["model"] = "TF-IDF(5000, 1-2gram) + LogisticRegression"

    # ── Model B: Signal + Text multimodal ────────────────────────────────────
    print("\n[B] Multimodal (Signal ResNet + TF-IDF) baseline...", flush=True)
    if os.path.exists(MODEL_PT):
        t0 = time.time()
        sig_model = ECGResNet1D(3).to(device)
        sig_model.load_state_dict(torch.load(MODEL_PT, map_location=device))
        sig_model.eval()

        # Limit to 3000 records per split for speed
        MAX_N = 3000
        tr_recs_sub = tr_recs[:MAX_N]; te_recs_sub = te_recs[:min(MAX_N,len(te_recs))]
        tr_labels_sub = tr_labels[:MAX_N]; te_labels_sub = te_labels[:min(MAX_N,len(te_labels))]
        tr_texts_sub  = tr_texts[:MAX_N];  te_texts_sub  = te_texts[:min(MAX_N,len(te_texts))]

        print(f"  Extracting signal embeddings (train {len(tr_recs_sub)})...", flush=True)
        tr_sig_emb = load_signals(tr_recs_sub, device, sig_model)
        print(f"  Extracting signal embeddings (test  {len(te_recs_sub)})...", flush=True)
        te_sig_emb = load_signals(te_recs_sub, device, sig_model)

        # TF-IDF features (same vectorizer)
        X_tr_tfidf_sub = tfidf.transform(tr_texts_sub).toarray().astype(np.float32)
        X_te_tfidf_sub = tfidf.transform(te_texts_sub).toarray().astype(np.float32)

        # Concatenate signal + text features
        X_tr_mm = np.concatenate([tr_sig_emb, X_tr_tfidf_sub], axis=1)
        X_te_mm = np.concatenate([te_sig_emb, X_te_tfidf_sub], axis=1)

        clf_mm = LogisticRegression(max_iter=500, C=0.1, random_state=42)
        clf_mm.fit(X_tr_mm, tr_labels_sub)
        te_probs_mm = clf_mm.predict_proba(X_te_mm)[:,1]
        print(f"  Total time: {time.time()-t0:.1f}s", flush=True)
        results["signal_text_fusion"] = report_metrics(te_labels_sub, te_probs_mm, "Signal+Text fusion")
        results["signal_text_fusion"]["n_test"] = len(te_recs_sub)
        results["signal_text_fusion"]["model"] = "ResNet512 + TF-IDF(5000) concat -> LogisticRegression"
    else:
        print("  Model weights not found — skipping multimodal", flush=True)
        results["signal_text_fusion"] = {"note": "Model weights not available"}

    out = os.path.join(OUT_DIR, "B5_baseline_results.json")
    with open(out,"w") as f: json.dump(results,f,indent=2)
    print(f"\nSaved: {out}", flush=True)

if __name__ == "__main__":
    main()
