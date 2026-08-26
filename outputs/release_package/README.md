<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `outputs/release_package/` - reproducibility bundle

Built by `70_build_release_package.py` (Stage P2.13). Empty until then.

Target layout (spec sections 3 and 9.14):

```
README.md        # how to reproduce every main-paper number, step by step
scripts/         # frozen copy of the Phase 2 scripts
configs/         # frozen copy of every locked YAML
notebooks/       # one .ipynb per main-paper figure
checksums.txt    # sha256 of every shipped config and script
```

Only this README and `checksums.txt` are tracked in git; the frozen copies are
build artifacts.
