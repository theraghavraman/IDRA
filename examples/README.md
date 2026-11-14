# Synthetic examples only

Every media frame and event in the valid example dataset was generated for this release. No real desktop, person, private account, screenshot or credential is included. The fake credential strings in tests/defect fixtures are test data, not real secrets.

- `synthetic_dataset/`: independently verified JSONL/CSV/manifest export with actual FFmpeg-encoded video and sampled PNGs.
- `sample-quality.json`: full-decode quality result for the clean fixture.
- `verification.json`: portable export re-import result.
- `defective-quality.json`: detected defects introduced deliberately in a temporary copied session.
- `deliberately_defective_fixture/`: intentionally malformed event journal and the expected defect recipe, not a clean dataset.

Regenerate with `python scripts/make_examples.py` in a clean source copy after explicitly moving/removing existing example outputs. The script refuses to overwrite the valid example dataset. Unit tests create their own temporary fixtures and do not depend on the timestamps or random IDs in these release examples.
