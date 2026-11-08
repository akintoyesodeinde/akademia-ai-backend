from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(slots=True)
class ExtractedSection:
    page_number: int
    section_title: str
    text: str


@dataclass(slots=True)
class ChunkPayload:
    chunk_index: int
    page_number: int
    section_title: str
    content_text: str
    token_count: int


@dataclass(slots=True)
class RetrievedPassage:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_version_number: int
    chunk_index: int
    page_number: int
    section_title: str | None
    content_text: str
    relevance_score: float


class CitationReference(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_version_number: int
    page_number: int
    section_title: str | None = None
    excerpt: str
    relevance_score: float


class GroundedTutorGenerationOutput(BaseModel):
    answer_text: str
    grounding_status: str = Field(
        default="grounded"
    )  # grounded, insufficient_course_material, integrity_restricted
    citations: list[CitationReference] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    model_id: str = "akademia-grounded-v1"
    prompt_version: str = "tutor-rag-v1"


class GeneratedPracticeOption(BaseModel):
    key: str
    text: str


class GeneratedPracticeQuestionSchema(BaseModel):
    question_type: str = "multiple_choice"
    prompt: str = Field(min_length=10)
    options: list[GeneratedPracticeOption] = Field(min_length=2)
    correct_answer: str = Field(min_length=1)
    explanation: str = Field(min_length=10)
    difficulty: str = "medium"
    cited_chunk_ids: list[UUID] = Field(min_length=1)


@dataclass(slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model_id: str
    model_version: str
    dimension: int
    total_tokens: int


class LanguageModel(Protocol):
    provider_name: str
    model_id: str

    async def generate_grounded_tutor_response(
        self,
        *,
        question: str,
        passages: list[RetrievedPassage],
        complexity_level: str = "standard",
        prompt_version: str = "tutor-rag-v1",
    ) -> GroundedTutorGenerationOutput: ...

    async def generate_practice_questions(
        self,
        *,
        objective_code: str,
        objective_title: str,
        difficulty: str,
        question_count: int,
        passages: list[RetrievedPassage],
        prompt_version: str = "practice-gen-v1",
    ) -> tuple[list[GeneratedPracticeQuestionSchema], int, int, int]: ...


class EmbeddingModel(Protocol):
    provider_name: str
    model_id: str
    model_version: str
    dimension: int

    async def embed_texts(self, texts: list[str]) -> EmbeddingResult: ...


class ContentExtractor(Protocol):
    def extract_and_chunk(
        self,
        *,
        content_bytes: bytes,
        content_type: str,
        filename: str,
        chunk_size_words: int = 120,
        chunk_overlap_words: int = 25,
    ) -> list[ChunkPayload]: ...


class CourseRetriever(Protocol):
    async def retrieve_authorized_passages(
        self,
        *,
        tenant_id: UUID,
        course_id: UUID,
        query: str,
        top_k: int = 5,
        max_context_tokens: int = 3000,
    ) -> list[RetrievedPassage]: ...


class AIUsageRecorder(Protocol):
    async def record_usage(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID | None,
        operation_type: str,
        provider_name: str,
        model_id: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> dict[str, Any]: ...
