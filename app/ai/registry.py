from app.ai.contracts import ContentExtractor, EmbeddingModel, LanguageModel
from app.ai.embeddings.service import (
    DeterministicSemanticEmbeddingModel,
    OpenAICompatibleEmbeddingModel,
)
from app.ai.providers.adapters import (
    DefaultContentExtractor,
    DeterministicGroundedLanguageModel,
    OpenAICompatibleLanguageModel,
)
from app.core.config import get_settings


def get_embedding_model() -> EmbeddingModel:
    settings = get_settings()
    if settings.ai_provider == "openai_compatible":
        return OpenAICompatibleEmbeddingModel()
    return DeterministicSemanticEmbeddingModel(
        model_id=settings.ai_embedding_model,
        dimension=settings.ai_embedding_dimension,
    )


def get_language_model() -> LanguageModel:
    settings = get_settings()
    if settings.ai_provider == "openai_compatible":
        return OpenAICompatibleLanguageModel()
    return DeterministicGroundedLanguageModel(model_id=settings.ai_chat_model)


def get_content_extractor() -> ContentExtractor:
    return DefaultContentExtractor()
