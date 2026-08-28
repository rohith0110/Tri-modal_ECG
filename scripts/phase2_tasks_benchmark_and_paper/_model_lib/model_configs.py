"""Generate and load `config/model_configs/*.yaml` (spec §5.8).

    ./ecg_env/Scripts/python.exe _model_lib/model_configs.py --emit
    ./ecg_env/Scripts/python.exe _model_lib/model_configs.py --list

§5.8 requires a YAML per (task, arch tier, lead subset). Writing ~100 of them by
hand would guarantee drift from `task_input_policy.yaml`, so they are DERIVED
from it: the tier list for a task is exactly the modality kinds that task is
allowed to read, crossed with the locked encoders. A config can therefore never
name a forbidden input, and adding a task or changing a policy regenerates the
matrix instead of requiring 100 edits.

Nothing here invents architecture. Every encoder, LR, dropout and embedding
width comes from `config/decision_phase2.yaml` (§5); a model config only selects
which locked encoder a run uses, which modality it reads, and the head shape.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                              # noqa: E402
from _dataset_lib.task_spec import TASKS, get_task                       # noqa: E402

MODEL_CONFIG_DIR = bc.CONFIG_DIR / "model_configs"
POLICY_PATH = bc.CONFIG_DIR / "task_input_policy.yaml"
DECISION_PATH = bc.CONFIG_DIR / "decision_phase2.yaml"

TASK_PREFIX = {key: key.split("_")[0] for key in TASKS}
IMAGE_TARGET = {
    "image_clean_lead2": (224, 672), "image_scanlike_lead2": (224, 672),
    "image_clean_12lead": (384, 512), "image_scanlike_12lead": (384, 512),
}
SIGNAL_LEADS = {"raw_lead2": 1, "preprocessed_lead2": 1,
                "raw_12lead": 12, "preprocessed_12lead": 12}
PRIMARY_SIGNAL = {"lead2": "preprocessed_lead2", "12lead": "preprocessed_12lead"}
PRIMARY_IMAGE = {"lead2": "image_clean_lead2", "12lead": "image_clean_12lead"}
EMBEDDING_TIER_TASKS = ("A5_cross_modal_verification", "B4_cross_modal_verification")

# §6.6 batch sizes, keyed by the family a run belongs to.
BATCH_SIZE = {"signal": 256, "signal_a4": 128, "signal_a6": 128,
              "image": 64, "text": 32, "multimodal": 16}
EPOCHS = {"signal": 30, "image": 30, "text": 20, "multimodal": 20}


def _policy() -> dict[str, Any]:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["tasks"]


def _decision() -> dict[str, Any]:
    return yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8"))


def _short(kind: str) -> str:
    """`preprocessed_lead2` -> `lead2_preprocessed`; `image_clean_12lead` -> `12lead_clean`."""
    if kind.startswith("image_"):
        _, rendering, layout = kind.split("_", 2)
        return f"{layout}_{rendering}"
    modality, layout = kind.rsplit("_", 1)
    return f"{layout}_{modality}"


def _batch_size(task: str, family: str) -> int:
    if family == "signal" and task == "A4_event_localization":
        return BATCH_SIZE["signal_a4"]
    if family == "signal" and task == "A6_risk_stratification":
        return BATCH_SIZE["signal_a6"]
    return BATCH_SIZE[family]


def _accumulation(task: str, family: str) -> int:
    # §6.6: A6 multimodal accumulates 4 steps to reach effective batch 64 for
    # calibration stability. Everything else is 1.
    return 4 if (task == "A6_risk_stratification" and family == "multimodal") else 1


def build_matrix() -> list[dict[str, Any]]:
    """Every (task, arch tier, lead subset) config, derived from the input policy."""
    policy = _policy()
    decision = _decision()
    lrs = decision["training"]["learning_rates"]
    configs: list[dict[str, Any]] = []

    for task_key, spec in TASKS.items():
        if spec.eval_only:
            continue                       # B6 reuses B4's trained models (§4.B.6)
        allowed = set(policy[task_key]["allowed_inputs"])
        signals = [k for k in SIGNAL_LEADS if k in allowed]
        images = [k for k in IMAGE_TARGET if k in allowed]
        has_text = "report_text" in allowed
        n_heads_out = sum(h.n_out for h in spec.heads)
        prefix = TASK_PREFIX[task_key]

        def base(arch_tier: str, lead_subset: str, family: str) -> dict[str, Any]:
            return {
                "task": task_key,
                "arch_tier": arch_tier,
                "lead_subset": lead_subset,
                "generated_by": "_model_lib/model_configs.py --emit",
                "spec": "docs/PHASE2_SOURCE_OF_TRUTH.md §5.8",
                "note": ("Architecture values are fixed by config/decision_phase2.yaml (§5). "
                         "This file selects encoders, input modalities and head shape only."),
                "head": {"n_out_total": int(n_heads_out),
                         "heads": [{"name": h.name, "kind": h.kind, "n_out": h.n_out}
                                   for h in spec.heads]},
                "train": {"epochs": EPOCHS[family],
                          "batch_size": _batch_size(task_key, family),
                          "accumulation_steps": _accumulation(task_key, family),
                          "patience": decision["training"]["early_stopping"]["patience_epochs"],
                          "learning_rates": dict(lrs)},
            }

        # -- signal-only tiers ------------------------------------------------
        for kind in signals:
            layout = "12lead" if kind.endswith("12lead") else "lead2"
            config = base(f"signal_resnet18_{_short(kind)}", layout, "signal")
            config["signal"] = {"encoder": "ECGResNet1D18", "n_leads": SIGNAL_LEADS[kind],
                                "input_modality": kind, "embed_dim": 512}
            configs.append(config)
            if task_key == "B2_noise_robustness":
                # §7.3: the same architecture trained with and without on-the-fly
                # corruption. regime_1 is the clean trainer, regime_2 augments.
                for regime, augment in (("regime_1", False), ("regime_2", True)):
                    variant = base(f"signal_resnet18_{_short(kind)}_{regime}", layout, "signal")
                    variant["signal"] = dict(config["signal"])
                    variant["regime"] = regime
                    variant["augment_regime_2"] = augment
                    configs.append(variant)

        # -- image-only tiers --------------------------------------------------
        for kind in images:
            layout = "12lead" if kind.endswith("12lead") else "lead2"
            height, width = IMAGE_TARGET[kind]
            config = base(f"image_resnet50_{_short(kind)}", layout, "image")
            config["image"] = {"encoder": "ImageResNet50", "input_modality": kind,
                               "target_h": height, "target_w": width,
                               # §5.3: augmentation on only for scan-like training
                               "augmentation": kind.startswith("image_scanlike"),
                               "embed_dim": 512}
            configs.append(config)

        # -- text-only tiers ---------------------------------------------------
        if has_text:
            for encoder, tier in (("BioClinicalBert", "text_bioclinicalbert"),
                                  ("TfidfTextEncoder", "text_tfidf")):
                config = base(tier, "none", "text")
                config["text"] = {"encoder": encoder, "max_length": 512, "embed_dim": 512}
                if encoder == "BioClinicalBert":
                    config["text"]["hf_id"] = decision["architecture"]["text_encoders"][
                        "primary"]["hf_id"]
                configs.append(config)

        # -- multimodal fusion -------------------------------------------------
        families_available = int(bool(signals)) + int(bool(images)) + int(has_text)
        if families_available >= 2:
            for layout in ("lead2", "12lead"):
                signal_kind = PRIMARY_SIGNAL[layout] if PRIMARY_SIGNAL[layout] in allowed else None
                image_kind = PRIMARY_IMAGE[layout] if PRIMARY_IMAGE[layout] in allowed else None
                if not signal_kind and not image_kind:
                    continue
                config = base(f"multimodal_fusion_{layout}", layout, "multimodal")
                if signal_kind:
                    config["signal"] = {"encoder": "ECGResNet1D18",
                                        "n_leads": SIGNAL_LEADS[signal_kind],
                                        "input_modality": signal_kind, "embed_dim": 512}
                if image_kind:
                    height, width = IMAGE_TARGET[image_kind]
                    config["image"] = {"encoder": "ImageResNet50",
                                       "input_modality": image_kind,
                                       "target_h": height, "target_w": width,
                                       "augmentation": False, "embed_dim": 512}
                if has_text:
                    config["text"] = {"encoder": "BioClinicalBert",
                                      "hf_id": decision["architecture"]["text_encoders"][
                                          "primary"]["hf_id"],
                                      "max_length": 512, "embed_dim": 512}
                config["fusion"] = {"head": "LateFusionMLP", "hidden_dims": [1024, 512],
                                    "dropout": 0.2, "mode": "end_to_end_fine_tuned"}
                configs.append(config)

                # -- the no-text leakage-controlled tier ----------------------
                # Plan A/B §5.3 ablation 6, Figure 2 and Appendix F: the no-text
                # multimodal run is the PRIMARY leakage-controlled setting, and
                # it has to be TRAINED, not simulated.
                #
                # §7.2 originally listed "no-text ablation" among the sweeps that
                # "re-evaluate the same trained model" without retraining. That
                # was written when fusion was frozen late fusion. Round 5.1 made
                # fusion end-to-end fine-tuned (`mode` above), and zeroing the
                # text branch of a jointly-trained encoder does not yield "the
                # same model without text" -- it yields a forward pass outside
                # the model's own training distribution. So the ablation gets its
                # own trained tier.
                #
                # Only where dropping text still leaves a FUSION: a task whose
                # only other modality is signal would collapse to the
                # signal-only tier that already exists (B5 is that case).
                if has_text and signal_kind and image_kind:
                    no_text = {k: v for k, v in config.items()}
                    no_text["arch_tier"] = f"multimodal_fusion_notext_{layout}"
                    no_text["train"] = dict(config["train"])
                    no_text["fusion"] = dict(config["fusion"])
                    no_text.pop("text", None)
                    no_text["ablation"] = "no_text"
                    no_text["ablation_spec"] = (
                        "Plan A/B §5.3 ablation 6 / Figure 2 / Appendix F — the "
                        "leakage-controlled multimodal setting, trained without "
                        "report text rather than evaluated with it zeroed")
                    configs.append(no_text)

                if task_key in EMBEDDING_TIER_TASKS:
                    # §4.A.5.7 / §4.B.4.7 "cosine similarity between frozen S/I/T
                    # embeddings" -- the no-fusion reference point.
                    similarity = dict(config)
                    similarity = {k: v for k, v in config.items()}
                    similarity["arch_tier"] = f"embedding_cosine_{layout}"
                    similarity["head_style"] = "similarity"
                    similarity["train"] = dict(config["train"])
                    configs.append(similarity)

    return configs


def config_filename(config: dict[str, Any]) -> str:
    prefix = TASK_PREFIX[config["task"]]
    return f"{prefix}_{config['arch_tier']}.yaml"


def emit(force: bool = False) -> list[Path]:
    MODEL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for config in build_matrix():
        path = MODEL_CONFIG_DIR / config_filename(config)
        text = yaml.safe_dump(config, sort_keys=False, width=100, allow_unicode=True)
        if path.exists() and not force and path.read_text(encoding="utf-8") == text:
            continue
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def load_model_config(path: str | Path) -> dict[str, Any]:
    """Read one model config and check it against the task's input policy."""
    from _dataset_lib.task_dataset import check_input_policy, plan_from_config

    candidate = Path(path)
    if not candidate.exists():
        candidate = MODEL_CONFIG_DIR / Path(path).name
    if not candidate.exists():
        raise FileNotFoundError(
            f"model config {path} not found. Run "
            "`_model_lib/model_configs.py --emit` to generate the §5.8 matrix.")
    config = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    get_task(config["task"])                       # raises on an unknown task
    check_input_policy(config["task"], plan_from_config(config).kinds())
    config["_path"] = str(candidate)
    return config


def _self_check() -> None:
    configs = build_matrix()
    names = [config_filename(c) for c in configs]
    assert len(names) == len(set(names)), "two configs claim the same filename"

    policy = _policy()
    for config in configs:
        allowed = set(policy[config["task"]]["allowed_inputs"])
        for block, key in (("signal", "input_modality"), ("image", "input_modality")):
            if config.get(block):
                kind = config[block][key]
                assert kind in allowed, f"{config_filename(config)} names forbidden {kind}"
        if config.get("text"):
            assert "report_text" in allowed, f"{config_filename(config)} reads forbidden text"

    per_task: dict[str, int] = {}
    for config in configs:
        per_task[config["task"]] = per_task.get(config["task"], 0) + 1
    # Every trainable task must have at least a signal-only and (where the
    # policy allows more than one family) a fusion tier.
    for task_key, spec in TASKS.items():
        if spec.eval_only:
            continue
        tiers = [c["arch_tier"] for c in configs if c["task"] == task_key]
        assert any(t.startswith("signal_resnet18") for t in tiers), f"{task_key}: no signal tier"
        if "report_text" in set(policy[task_key]["allowed_inputs"]):
            assert "text_bioclinicalbert" in tiers and "text_tfidf" in tiers, \
                f"{task_key}: §5.4 requires BOTH text encoders"

    assert not any(c["task"] == "B6_difficulty_stratified" for c in configs), \
        "B6 is evaluation-time only (§4.B.6) and must have no trained config"

    for task_key in sorted(per_task):
        print(f"  {task_key:32s} {per_task[task_key]:2d} configs")
    print(f"model_configs self-check: PASS  ({len(configs)} configs over "
          f"{len(per_task)} trainable tasks)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the §5.8 model-config matrix")
    parser.add_argument("--emit", action="store_true", help="write the YAMLs")
    parser.add_argument("--force", action="store_true", help="rewrite unchanged files too")
    parser.add_argument("--list", action="store_true", help="print the matrix")
    args = parser.parse_args()

    if args.emit:
        written = emit(force=args.force)
        print(f"wrote {len(written)} config(s) into {MODEL_CONFIG_DIR}")
        for path in written[:10]:
            print(f"  {path.name}")
        if len(written) > 10:
            print(f"  ... and {len(written) - 10} more")
        return 0
    if args.list:
        for config in build_matrix():
            print(config_filename(config))
        return 0
    _self_check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
