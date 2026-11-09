# Akademia AI — AI Evaluation & Quality Gates (`AI_EVALUATION.md`)

## 1. Automated RAG & Safety Benchmark Harness (`app/ai/evaluation/service.py`)

`AIEvaluationHarness` evaluates the end-to-end retrieval, grounding, citation verification, cross-tenant isolation, and structured practice generation pipeline against a multi-tenant benchmark dataset (`Tenant A` target course vs. `Tenant B` canary/secret documents) and persists the results in `ai_evaluation_runs`.

---

## 2. Enforced Quality Gate Metrics

| Metric | Target Threshold | Purpose |
|---|---|---|
| `retrieval_recall_at_5` | `>= 0.80` | Verifies top-5 retrieved chunks contain the ground-truth course passage |
| `citation_authorization_rate` | `== 1.00` | Verifies 100% of emitted citations map to authorized chunks in the caller's tenant & course |
| `groundedness_rate` | `>= 0.85` | Verifies responses are grounded in retrieved passages or appropriately flag `insufficient_course_context` |
| `answer_relevance_score` | `>= 0.80` | Measures semantic alignment between the learner's question and the tutor's explanation |
| `unauthorized_leak_count` | `== 0` | Zero tolerance for cross-tenant or cross-course chunk leakage under adversarial queries |
| `structured_output_validity_rate` | `== 1.00` | Verifies 100% of generated practice question drafts pass Pydantic schema and guardrail validation |

---

## 3. Running the Evaluation Suite

- **Via Automated Pytest Gate**:
  ```bash
  uv run pytest tests/ai_evaluation/test_ai_quality_gates.py -v
  ```
- **Via Platform Operator API**:
  `POST /api/v1/operations/platform/ai-evaluations/run` with `{ "suite_name": "ci-rag-safety-and-citation-benchmark-v1" }`.
