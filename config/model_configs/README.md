<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `config/model_configs/` - one YAML per (task, arch tier, lead subset)

Authored at Stage P2.5 preparation; consumed by `30_train.py --model-config`.
Empty until then.

The architecture values are NOT free parameters - they are fixed by
`config/decision_phase2.yaml` (spec section 5). A model config selects which of
the locked encoders a run uses, which input modality it reads, and the head
shape; it does not invent new architecture. Any `train:` block override is
captured by the section 11 audit so a reviewer sees "task X overrode default
LR - here's why."

Shape (spec section 5.8):

```yaml
task: A1_ecg_diagnosis
arch_tier: multimodal_fusion
lead_subset: 12-lead
signal: {encoder: ECGResNet1D18, n_leads: 12, input_modality: preprocessed_12lead, embed_dim: 512}
image:  {encoder: ImageResNet50, input_modality: image_clean_12lead, target_h: 384, target_w: 512, augmentation: false}
text:   {encoder: BioClinicalBert, hf_id: emilyalsentzer/Bio_ClinicalBERT, max_length: 512}
fusion: {head: LateFusionMLP, hidden_dims: [1024, 512], dropout: 0.2}
head:   {output: sigmoid, n_classes: 5}
loss: BCEWithLogitsLoss
class_weights: from_train
```
