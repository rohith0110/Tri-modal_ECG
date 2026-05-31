"""
11b_eval_B2_regime2.py — B2 corruption curve for regime-2 (noise-augmented) model.
Output: outputs/tables/B2_regime2_curve.json
"""
import os, importlib.util

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "r1", os.path.join(here, "11_eval_B2_regime1.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.run_curve(
        "../outputs/model_runs/B2_regime2/B2_regime2_seed42_model.pt",
        "../outputs/tables/B2_regime2_curve.json",
        "regime2"
    )

if __name__ == "__main__":
    main()
