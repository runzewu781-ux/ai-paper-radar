from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    hf_token: str = ""
    github_token: str = ""
    s2_api_key: str = ""
    database_url: str = "sqlite:///./data/paper_radar.db"

    arxiv_request_interval: float = 3.0
    arxiv_max_results_per_page: int = 100
    arxiv_categories: list[str] = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]
    arxiv_default_days: int = 7

    hf_api_base: str = "https://huggingface.co/api"
    hf_proxy: str = ""
    github_api_base: str = "https://api.github.com"
    s2_api_base: str = "https://api.semanticscholar.org/graph/v1"
    s2_batch_size: int = 500
    s2_rate_limit: float = 1.0

    llm_api_base: str = "https://api.atlascloud.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen/qwen3-32b"

    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
