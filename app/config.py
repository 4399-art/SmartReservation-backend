from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_EXPIRE_HOURS: int
    JWT_ALGORITHM: str
    CORS_ORIGINS: str = ""
    SERVER_HOST: str = "http://127.0.0.1:8000"
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = ""
    EMBEDDING_PROVIDER: str = "openai"
    DASHSCOPE_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


MAX_FILE_SIZE = 100 * 1024 * 1024
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip",
    ".md",
}

CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

RAG_COLLECTION_NAME = "rag_documents"
RAG_UPLOAD_DIR = BASE_DIR / "rag_uploads"
RAG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()