import io
import json
import re
import time

import httpx
from pypdf import PdfReader

from app.ai.contracts import (
    ChunkPayload,
    CitationReference,
    GeneratedPracticeOption,
    GeneratedPracticeQuestionSchema,
    GroundedTutorGenerationOutput,
    RetrievedPassage,
)
from app.ai.safety.guardrails import (
    detect_prompt_injection,
    sanitize_passage_text,
    verify_and_filter_citations,
)
from app.core.config import get_settings
from app.shared.errors import ExternalProviderError, ValidationAppError


class DefaultContentExtractor:
    """Extracts text from PDF, Markdown, or Plaintext documents and chunks with section/page metadata."""

    def extract_and_chunk(
        self,
        *,
        content_bytes: bytes,
        content_type: str,
        filename: str,
        chunk_size_words: int = 120,
        chunk_overlap_words: int = 25,
    ) -> list[ChunkPayload]:
        normalized_ct = content_type.split(";")[0].strip().lower()
        pages: list[tuple[int, str]] = []

        if normalized_ct == "application/pdf":
            try:
                reader = PdfReader(io.BytesIO(content_bytes))
                for idx, page in enumerate(reader.pages, start=1):
                    txt = (page.extract_text() or "").strip()
                    if txt:
                        pages.append((idx, txt))
            except Exception as exc:
                raise ValidationAppError(f"Failed to parse PDF document: {exc}") from exc
        else:
            try:
                decoded = content_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValidationAppError("Text document must be valid UTF-8.") from exc
            # Split by form-feed or treat as page 1..N blocks
            raw_pages = decoded.split("\f") if "\f" in decoded else [decoded]
            for idx, page_txt in enumerate(raw_pages, start=1):
                if page_txt.strip():
                    pages.append((idx, page_txt.strip()))

        if not pages:
            raise ValidationAppError("Document contains no extractable text content.")

        chunks: list[ChunkPayload] = []
        chunk_idx = 0
        current_section = "Overview"

        for page_num, page_text in pages:
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page_text) if p.strip()]
            buffer_words: list[str] = []
            for para in paragraphs:
                heading_match = re.match(r"^#{1,3}\s+(.+)$", para.splitlines()[0])
                if heading_match:
                    if buffer_words:
                        content_str = " ".join(buffer_words)
                        chunks.append(
                            ChunkPayload(
                                chunk_index=chunk_idx,
                                page_number=page_num,
                                section_title=current_section,
                                content_text=content_str,
                                token_count=len(buffer_words),
                            )
                        )
                        chunk_idx += 1
                        buffer_words = []
                    current_section = heading_match.group(1).strip()[:120]

                words = para.split()
                buffer_words.extend(words)
                while len(buffer_words) >= chunk_size_words:
                    slice_words = buffer_words[:chunk_size_words]
                    chunks.append(
                        ChunkPayload(
                            chunk_index=chunk_idx,
                            page_number=page_num,
                            section_title=current_section,
                            content_text=" ".join(slice_words),
                            token_count=len(slice_words),
                        )
                    )
                    chunk_idx += 1
                    step = max(1, chunk_size_words - chunk_overlap_words)
                    buffer_words = buffer_words[step:]

            if buffer_words:
                chunks.append(
                    ChunkPayload(
                        chunk_index=chunk_idx,
                        page_number=page_num,
                        section_title=current_section,
                        content_text=" ".join(buffer_words),
                        token_count=len(buffer_words),
                    )
                )
                chunk_idx += 1

        return chunks


class DeterministicGroundedLanguageModel:
    """Course-grounded deterministic language model adapter for reproducible RAG & practice generation."""

    def __init__(self, model_id: str = "akademia-grounded-v1") -> None:
        self.provider_name = "deterministic"
        self.model_id = model_id

    async def generate_grounded_tutor_response(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        complexity_level: str = "standard",
        prompt_version: str = "tutor-rag-v1",
    ) -> GroundedTutorGenerationOutput:
        start = time.perf_counter()
        if detect_prompt_injection(question):
            return GroundedTutorGenerationOutput(
                answer_text=(
                    "I cannot fulfill requests that attempt to override safety instructions, "
                    "expose system prompts, or access unauthorized tenant or assessment data. "
                    "Please ask a question about the authorized course materials."
                ),
                grounding_status="insufficient_course_material",
                citations=[],
                input_tokens=max(10, len(question.split())),
                output_tokens=34,
                latency_ms=max(1, int((time.perf_counter() - start) * 1000)),
                model_id=self.model_id,
                prompt_version=prompt_version,
            )

        query_terms = {
            w
            for w in re.findall(r"[a-z0-9]+", question.lower())
            if len(w) > 2
            and w
            not in {
                "what",
                "how",
                "why",
                "when",
                "where",
                "which",
                "who",
                "the",
                "and",
                "for",
                "with",
                "does",
                "explain",
                "describe",
                "tell",
                "about",
                "course",
            }
        }

        # A passage supports the question only if it covers a meaningful share of the
        # question's content terms (a single incidental shared word is not grounding).
        min_overlap_ratio = 0.25
        supported_passages: list[RetrievedPassage] = []
        for p in passages:
            passage_words = set(re.findall(r"[a-z0-9]+", p.content_text.lower()))
            overlap = len(query_terms & passage_words)
            overlap_ratio = overlap / len(query_terms) if query_terms else 0.0
            if overlap_ratio >= min_overlap_ratio or p.relevance_score >= 0.35:
                supported_passages.append(p)

        if not supported_passages or not query_terms:
            return GroundedTutorGenerationOutput(
                answer_text=(
                    "The approved course materials do not contain sufficient information to answer "
                    "this question. Please refer to the published lessons or ask your instructor."
                ),
                grounding_status="insufficient_course_material",
                citations=[],
                input_tokens=max(15, len(question.split())),
                output_tokens=28,
                latency_ms=max(1, int((time.perf_counter() - start) * 1000)),
                model_id=self.model_id,
                prompt_version=prompt_version,
            )

        top_passages = supported_passages[:3]
        synthesized_points: list[str] = []
        raw_citations: list[CitationReference] = []
        for idx, p in enumerate(top_passages, start=1):
            clean_txt = sanitize_passage_text(p.content_text)
            synthesized_points.append(
                f"[{idx}] ({p.document_title}, p.{p.page_number}"
                f"{f' — {p.section_title}' if p.section_title else ''}): {clean_txt}"
            )
            raw_citations.append(
                CitationReference(
                    chunk_id=p.chunk_id,
                    document_id=p.document_id,
                    document_title=p.document_title,
                    document_version_number=p.document_version_number,
                    page_number=p.page_number,
                    section_title=p.section_title,
                    excerpt=clean_txt[:240],
                    relevance_score=round(p.relevance_score, 4),
                )
            )

        verified_citations = verify_and_filter_citations(raw_citations, passages)
        prefix = (
            "Based on the authorized course materials"
            if complexity_level == "standard"
            else f"Based on the authorized course materials ({complexity_level} level)"
        )
        answer_text = f"{prefix}:\n\n" + "\n\n".join(synthesized_points)
        in_tokens = len(question.split()) + sum(len(p.content_text.split()) for p in top_passages)
        out_tokens = len(answer_text.split())

        return GroundedTutorGenerationOutput(
            answer_text=answer_text,
            grounding_status="grounded",
            citations=verified_citations,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_ms=max(1, int((time.perf_counter() - start) * 1000)),
            model_id=self.model_id,
            prompt_version=prompt_version,
        )

    async def generate_practice_questions(
        self,
        *,
        objective_code: str,
        objective_title: str,
        difficulty: str,
        question_count: int,
        passages: list[RetrievedPassage],
        prompt_version: str = "practice-gen-v1",
    ) -> tuple[list[GeneratedPracticeQuestionSchema], int, int, int]:
        start = time.perf_counter()
        if not passages:
            raise ValidationAppError(
                "Cannot generate grounded practice questions without authorized course passages."
            )

        drafts: list[GeneratedPracticeQuestionSchema] = []
        for idx in range(question_count):
            passage = passages[idx % len(passages)]
            clean_excerpt = sanitize_passage_text(passage.content_text)
            first_sentence = clean_excerpt.split(".")[0].strip()
            if len(first_sentence) < 15:
                first_sentence = clean_excerpt[:140].strip()

            prompt_text = (
                f"[{objective_code}] According to '{passage.document_title}' "
                f"(p.{passage.page_number}), which statement accurately reflects {objective_title} "
                f"(Practice Item #{idx + 1})?"
            )
            options = [
                GeneratedPracticeOption(key="A", text=first_sentence),
                GeneratedPracticeOption(
                    key="B",
                    text="An unsupported claim that contradicts the approved course material.",
                ),
                GeneratedPracticeOption(
                    key="C",
                    text="A policy unrelated to the learning objective or course curriculum.",
                ),
                GeneratedPracticeOption(
                    key="D",
                    text="None of the principles described in the course reference material.",
                ),
            ]
            drafts.append(
                GeneratedPracticeQuestionSchema(
                    question_type="multiple_choice",
                    prompt=prompt_text,
                    options=options,
                    correct_answer="A",
                    explanation=(
                        f"Grounded in {passage.document_title} (p.{passage.page_number}): "
                        f"{first_sentence}"
                    ),
                    difficulty=difficulty,
                    cited_chunk_ids=[passage.chunk_id],
                )
            )

        in_tokens = sum(len(p.content_text.split()) for p in passages) + 40
        out_tokens = question_count * 75
        latency_ms = max(1, int((time.perf_counter() - start) * 1000))
        return drafts, in_tokens, out_tokens, latency_ms


class OpenAICompatibleLanguageModel:
    """OpenAI-compatible chat completion adapter behind the provider-neutral LanguageModel protocol."""

    def __init__(self) -> None:
        settings = get_settings()
        self.provider_name = "openai_compatible"
        self.model_id = settings.ai_chat_model
        self.api_key = settings.ai_api_key
        self.base_url = settings.ai_base_url.rstrip("/")
        self.timeout = settings.ai_request_timeout_seconds
        self._fallback = DeterministicGroundedLanguageModel(model_id=self.model_id)

    async def generate_grounded_tutor_response(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        complexity_level: str = "standard",
        prompt_version: str = "tutor-rag-v1",
    ) -> GroundedTutorGenerationOutput:
        if not self.api_key:
            raise ExternalProviderError("AI_API_KEY is required when AI_PROVIDER=openai_compatible.")
        if detect_prompt_injection(question) or not passages:
            return await self._fallback.generate_grounded_tutor_response(
                question=question,
                passages=passages,
                complexity_level=complexity_level,
                prompt_version=prompt_version,
            )

        start = time.perf_counter()
        context_block = "\n\n".join(
            f"CHUNK_ID={p.chunk_id} | DOC={p.document_title} | PAGE={p.page_number}\n{sanitize_passage_text(p.content_text)}"
            for p in passages
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model_id,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Answer strictly from the provided course passages. "
                                    "Return JSON with keys: answer_text, grounding_status, cited_chunk_ids."
                                ),
                            },
                            {
                                "role": "user",
                                "content": f"Context:\n{context_block}\n\nQuestion: {question}",
                            },
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                raw_json = json.loads(body["choices"][0]["message"]["content"])
                usage = body.get("usage", {})
                raw_cits = [
                    CitationReference(
                        chunk_id=p.chunk_id,
                        document_id=p.document_id,
                        document_title=p.document_title,
                        document_version_number=p.document_version_number,
                        page_number=p.page_number,
                        section_title=p.section_title,
                        excerpt=p.content_text[:240],
                        relevance_score=p.relevance_score,
                    )
                    for p in passages
                ]
                verified = verify_and_filter_citations(raw_cits, passages)
                return GroundedTutorGenerationOutput(
                    answer_text=raw_json.get("answer_text", ""),
                    grounding_status=raw_json.get("grounding_status", "grounded"),
                    citations=verified,
                    input_tokens=int(usage.get("prompt_tokens", 50)),
                    output_tokens=int(usage.get("completion_tokens", 50)),
                    latency_ms=max(1, int((time.perf_counter() - start) * 1000)),
                    model_id=self.model_id,
                    prompt_version=prompt_version,
                )
            except Exception as exc:
                raise ExternalProviderError(f"Language model provider error: {exc}") from exc

    async def generate_practice_questions(
        self,
        *,
        objective_code: str,
        objective_title: str,
        difficulty: str,
        question_count: int,
        passages: list[RetrievedPassage],
        prompt_version: str = "practice-gen-v1",
    ) -> tuple[list[GeneratedPracticeQuestionSchema], int, int, int]:
        if not self.api_key:
            raise ExternalProviderError("AI_API_KEY is required when AI_PROVIDER=openai_compatible.")
        return await self._fallback.generate_practice_questions(
            objective_code=objective_code,
            objective_title=objective_title,
            difficulty=difficulty,
            question_count=question_count,
            passages=passages,
            prompt_version=prompt_version,
        )
