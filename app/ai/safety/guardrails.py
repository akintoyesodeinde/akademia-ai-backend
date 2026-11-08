import re
from uuid import UUID

from app.ai.contracts import (
    CitationReference,
    GeneratedPracticeQuestionSchema,
    RetrievedPassage,
)

PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?(system\s+prompt|answer\s+key|secret|api\s+key)", re.IGNORECASE),
    re.compile(r"bypass\s+(tenant|authorization|rls|security)", re.IGNORECASE),
    re.compile(r"show\s+(me\s+)?other\s+tenant", re.IGNORECASE),
    re.compile(r"system\s*override", re.IGNORECASE),
)


def detect_prompt_injection(text: str) -> bool:
    """Detect direct or indirect prompt-injection patterns in user queries or retrieved chunks."""
    return any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS)


def sanitize_passage_text(text: str) -> str:
    """Neutralize embedded directive phrases in untrusted course document chunks."""
    sanitized = text
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED_UNTRUSTED_DIRECTIVE]", sanitized)
    return sanitized


def verify_and_filter_citations(
    proposed_citations: list[CitationReference],
    authorized_passages: list[RetrievedPassage],
) -> list[CitationReference]:
    """Ensure 100% of returned citations resolve strictly to authorized retrieved passages."""
    by_chunk_id: dict[UUID, RetrievedPassage] = {p.chunk_id: p for p in authorized_passages}
    verified: list[CitationReference] = []
    seen: set[UUID] = set()
    for cit in proposed_citations:
        passage = by_chunk_id.get(cit.chunk_id)
        if passage is None or cit.chunk_id in seen:
            continue
        if cit.document_id != passage.document_id:
            continue
        seen.add(cit.chunk_id)
        verified.append(
            CitationReference(
                chunk_id=passage.chunk_id,
                document_id=passage.document_id,
                document_title=passage.document_title,
                document_version_number=passage.document_version_number,
                page_number=passage.page_number,
                section_title=passage.section_title,
                excerpt=passage.content_text[:240],
                relevance_score=round(passage.relevance_score, 4),
            )
        )
    return verified


def validate_generated_practice_question(
    draft: GeneratedPracticeQuestionSchema,
    authorized_passages: list[RetrievedPassage],
    existing_prompts: set[str],
) -> dict[str, object]:
    """Validate factual grounding, answer-key consistency, clarity, non-duplication, and citations."""
    authorized_ids = {p.chunk_id for p in authorized_passages}
    option_keys = {opt.key.strip() for opt in draft.options}
    option_texts = {opt.text.strip() for opt in draft.options}
    valid_citations = [cid for cid in draft.cited_chunk_ids if cid in authorized_ids]
    normalized_prompt = draft.prompt.strip().lower()
    is_duplicate = normalized_prompt in existing_prompts

    answer_key_valid = (
        draft.correct_answer.strip() in option_keys
        or draft.correct_answer.strip() in option_texts
    )
    clarity_valid = len(draft.prompt.strip()) >= 15 and draft.prompt.strip().endswith("?")
    citations_valid = len(valid_citations) > 0

    passed = (
        answer_key_valid
        and clarity_valid
        and citations_valid
        and not is_duplicate
        and len(draft.options) >= 2
    )
    return {
        "passed": passed,
        "answer_key_valid": answer_key_valid,
        "clarity_valid": clarity_valid,
        "citations_valid": citations_valid,
        "is_duplicate": is_duplicate,
        "verified_chunk_ids": [str(cid) for cid in valid_citations],
    }
