import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import EmbeddingModel, RetrievedPassage
from app.modules.content.models import ChunkEmbedding, Document, DocumentChunk


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    return max(0.0, min(1.0, dot))


class PgVectorCourseRetriever:
    """Retrieves only authorized, ready-status course chunks within the active tenant RLS context."""

    def __init__(self, session: AsyncSession, embedding_model: EmbeddingModel) -> None:
        self.session = session
        self.embedding_model = embedding_model

    async def retrieve_authorized_passages(
        self,
        *,
        tenant_id: UUID,
        course_id: UUID,
        query: str,
        top_k: int = 5,
        max_context_tokens: int = 3000,
    ) -> list[RetrievedPassage]:
        embed_res = await self.embedding_model.embed_texts([query])
        query_vec = embed_res.vectors[0]
        query_words = {
            w
            for w in re.findall(r"[a-z0-9]+", query.lower())
            if len(w) > 2
        }

        # Strict tenant_id + course_id + Document.status == 'ready' + indexing_status == 'indexed'
        stmt = (
            select(
                DocumentChunk,
                Document.title.label("doc_title"),
                Document.current_version_number.label("doc_ver"),
                ChunkEmbedding.embedding,
                ChunkEmbedding.embedding.cosine_distance(query_vec).label("cosine_dist"),
            )
            .join(
                Document,
                (Document.id == DocumentChunk.document_id)
                & (Document.tenant_id == DocumentChunk.tenant_id),
            )
            .join(
                ChunkEmbedding,
                (ChunkEmbedding.chunk_id == DocumentChunk.id)
                & (ChunkEmbedding.tenant_id == DocumentChunk.tenant_id),
            )
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.course_id == course_id,
                Document.status == "ready",
                ChunkEmbedding.indexing_status == "indexed",
                ChunkEmbedding.embedding_model_id == self.embedding_model.model_id,
            )
            .order_by("cosine_dist")
            .limit(top_k * 3)
        )

        rows = (await self.session.execute(stmt)).all()
        candidates: list[RetrievedPassage] = []
        for chunk, doc_title, doc_ver, emb_vec, cosine_dist in rows:
            vec_list = list(emb_vec) if emb_vec is not None else []
            vec_sim = (
                max(0.0, 1.0 - float(cosine_dist))
                if cosine_dist is not None
                else _cosine_similarity(query_vec, vec_list)
            )
            chunk_words = set(re.findall(r"[a-z0-9]+", chunk.content_text.lower()))
            lexical_overlap = (
                len(query_words & chunk_words) / max(1, len(query_words))
                if query_words
                else 0.0
            )
            hybrid_score = round(0.55 * vec_sim + 0.45 * lexical_overlap, 4)
            candidates.append(
                RetrievedPassage(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=doc_title,
                    document_version_number=doc_ver,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    content_text=chunk.content_text,
                    relevance_score=hybrid_score,
                )
            )

        candidates.sort(key=lambda c: c.relevance_score, reverse=True)

        selected: list[RetrievedPassage] = []
        running_tokens = 0
        for cand in candidates:
            est_tokens = max(1, len(cand.content_text.split()))
            if running_tokens + est_tokens > max_context_tokens:
                break
            selected.append(cand)
            running_tokens += est_tokens
            if len(selected) >= top_k:
                break

        return selected
