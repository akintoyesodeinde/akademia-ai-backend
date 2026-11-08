import pytest
from app.ai.evaluation.service import AIEvaluationHarness


@pytest.mark.asyncio
async def test_ai_evaluation_quality_gates_meet_release_targets() -> None:
    """Verify Part 11.1 quality gates on the curated evaluation dataset:
    - Retrieval Recall@5 >= 0.85
    - Citation resolution and authorization == 100% (1.0)
    - Groundedness >= 0.90
    - Answer relevance >= 0.90
    - Unauthorized content entering model context == 0
    - Structured-output validity >= 0.99
    """
    harness = AIEvaluationHarness()
    report = await harness.run_suite()

    assert report["sample_size"] >= 9
    assert report["retrieval_recall_at_5"] >= 0.85
    assert report["citation_authorization_rate"] == 1.0
    assert report["groundedness_score"] >= 0.90
    assert report["answer_relevance_score"] >= 0.90
    assert report["unauthorized_leak_count"] == 0
    assert report["structured_validity_rate"] >= 0.99
    assert report["practice_questions_valid"] == report["practice_questions_evaluated"]
