# Entity Resolution Subsystem

## 1. Design Principles
- **Observable Signals Only**: Production candidate generation (`entity_resolution/candidate_generation.py`) and live ER (`backend/app/services/er_live_service.py`) operate strictly on observable attributes (`name`, `alias`, `phone`, `device_id`, `imei`, `vehicle`, `location`, `contacts`). Zero ground-truth files or cluster tokens are accessed in production blocking or feature extraction.
- **No Auto-Merge**: Matches generate provisional `IdentityHypothesis` rows (`CANDIDATE` / `PENDING_REVIEW`) that require explicit human adjudication (`ACCEPTED` / `DISPUTED` / `REJECTED`) with rationale.
- **Public Infrastructure Safeguard**: Shared public Wi-Fi IPs alone never trigger candidate blocking and carry an explicit feature flag (`shared_ip_is_public_infra`).

## 2. Live Cross-Case Pipeline
1. `build_observable_profiles_from_db()` aggregates ACTIVE `PERSONS`, `CDR`, `DEVICE`, `VEHICLE`, and `TRAVEL` normalized records from PostgreSQL.
2. Conservative blocking filters cross-case pairs by shared normalized phones, personal devices, IMEIs, vehicles, name similarity (`lev >= 0.65` or `tok >= 0.5`), or alias similarity.
3. `EntityResolutionPredictor.predict_pair()` computes 28 pairwise features, including Sentence Transformer cosine similarity (with `_DeterministicHashEncoder` 384-d offline fallback in `entity_resolution/embeddings.py` when HF/sentence_transformers weights are absent), predicts via XGBoost (`er-xgb-1.0.0`), and attaches supporting/conflicting explanations.
4. Hypotheses with `match_probability >= 0.70` are also surfaced as `LEAD_ER_*` investigation leads.
5. Re-evaluating preserves existing human review statuses (`ACCEPTED`, `REJECTED`, `DISPUTED`).
