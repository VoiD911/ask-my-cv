# « Interroge mon CV » — plan 1b-bis : faux positifs du classifieur dans le domaine — plan d'implémentation

**Objectif :** corriger les faux positifs du classifieur `model-v1.0.0` sur les questions de recruteurs au tutoiement ou en « you » (12 % mesurés sur 50 questions du domaine), et verrouiller cette propriété par une nouvelle porte d'évaluation.

Plan : [2026-09-25-ask-my-cv-1b-bis-domain-false-positives.md](../plans/2026-09-25-ask-my-cv-1b-bis-domain-false-positives.md)

## Tâches 1-2

### Implémentation

#### 2026-09-25 18:49 · general-purpose · sonnet

- Description : Plan 1b-bis Tasks 1-2
- Commits : [`38dfc2c`](https://github.com/VoiD911/ask-my-cv/commit/38dfc2c01b94f26d614013ebe6c998b188ff7c13), [`2eb0ee9`](https://github.com/VoiD911/ask-my-cv/commit/2eb0ee97947129f7883f28fd5feb6a40af2649c0)

<details><summary>Rapport</summary>

## Report

**Status: Tasks 1 and 2 complete, committed on `main`, not pushed.**

`git log --oneline -2`:
```
38dfc2c feat(ml): porte sur les faux positifs du domaine et données au tutoiement
2eb0ee9 fix: locale en_US.UTF-8 pour le modèle ONNX dans l'image, test de fumée du conteneur en CI
```

**Line counts:**
- `ml/data/handwritten.jsonl`: 138 lines (91 existing + 47 new, extracted verbatim from the plan via a Python script, UTF-8, `\n` newlines, final newline)
- `ml/data/recruiter_eval.jsonl`: 50 lines (new file, same extraction method)

**Gates (before commit):**
- `ruff format .` → 1 file reformatted (ml/dataset.py line wrap), rest unchanged
- `ruff check .` → All checks passed
- `pyright` → 0 errors, 0 warnings, 0 informations
- `pytest -q` → **169 passed** (166 baseline + 3 new tests: `test_real_recruiter_eval_is_legit_and_disjoint_from_training`, `test_domain_false_positive_fails_the_gate`, `test_empty_domain_set_fails_the_gate`)

**Step 4 real training** (`python -m ml.train --version v0.0.0 --out <temp dir, since deleted>`):
```
OK  deepset_recall = 0.8167 (limite 0.8)
OK  deepset_fpr = 0.0000 (limite 0.05)
OK  gandalf_recall = 0.9730 (limite 0.95)
OK  domain_fpr = 0.0000 (limite 0.02)
OK  adversarial_pass_rate = 1.0000 (limite 1.0)
OK  onnx_parity_max_diff = 0.0000 (limite 0.001)
```
These closely match the plan's "Mesures" table for v1.1.0 (deepset recall ≈0.817, gandalf ≈0.973, domain_fpr = 0.000). Temp output directory was removed afterward.

**Changes made:**
- `ml/dataset.py`: added `RECRUITER_EVAL_PATH`, `Datasets.eval_domain` field (default empty list), `build_datasets` now takes a 5th `domain` arg, reads it via `read_jsonl`, and raises `ValueError` on any domain/train text overlap (mirroring the adversarial leakage check).
- `ml/evaluate.py`: added `Gates.domain_max_fpr = 0.02`; `evaluate()` now appends domain texts to `texts` (order: deepset → gandalf → adversarial → domain) for parity checking, computes `domain_fpr` (empty set forces `1.0`/fail), and inserts a `domain_fpr` `Check` right after `gandalf_recall`.
- `ml/gates.yaml`: added `domain_max_fpr: 0.02` with the comment from the plan.
- `ml/train.py`: `main()` passes `RECRUITER_EVAL_PATH` to `build_datasets`; `render_model_card` gained the domain-dataset line under "Données" and the recall-margin note under "Limites connues".
- `tests/training/test_dataset.py`, `test_evaluate.py`, `test_train.py`: updated per the plan's Step 1 spec (new `RECRUITER_EVAL_PATH` import/test, `domain` param plumbed through `build_datasets` tests, `eval_domain` added to all `tiny_datasets()`/`Datasets(...)` constructions that must pass the gate, new `["...", "domain_fpr", ...]` check-name ordering assertion, new `test_repository_gates_match_api_threshold` assertion, and the two new domain-gate tests).

No concerns — nothing deviated from the plan; no thresholds or data were altered beyond what the plan specified. Task 3 (push, `train.yml` run, promotion PR) was intentionally left untouched per the instructions.

</details>
