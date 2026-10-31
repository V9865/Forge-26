"""Configuration module for EmberRoute.

Loads settings from .env file and environment variables.
Provides a frozen Settings dataclass with sensitive keys masked in repr/str.
"""

from dataclasses import dataclass, fields
from functools import lru_cache
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Frozen application configuration settings."""

    # API Keys & Endpoints
    FIRMS_MAP_KEY: str = ""
    LLM_CHAIN: str = "groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant,ollama:qwen2.5:7b-instruct"
    LLM_PLANNER_MODEL: str = "groq:llama-3.1-8b-instant"
    LLM_BRIEFING_MODEL: str = "groq:llama-3.3-70b-versatile"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"

    # LLM & Polling
    LLM_DAILY_TOKEN_BUDGET: int = 100000
    LLM_TIMEOUT_S: int = 20
    POLL_S: int = 60

    # Cache & Simulation
    CACHE_DIR: str = ".cache"
    SIMULATE_API_FAILURE: str = ""

    # Logging & Server
    LOG_LEVEL: str = "INFO"
    API_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173"

    # Network & Simulation Defaults
    HTTP_TIMEOUT_S: int = 20
    HTTP_RETRIES: int = 3
    WEATHER_TTL_S: int = 600
    FIRES_TTL_S: int = 900
    GRID_RES_M: int = 90
    MAX_GRID_CELLS: int = 400
    HORIZON_MIN: int = 720

    def __repr__(self) -> str:
        secret_keys = {"FIRMS_MAP_KEY", "GROQ_API_KEY"}
        attrs = []
        for f in fields(self):
            val = getattr(self, f.name)
            if f.name in secret_keys or "KEY" in f.name or "SECRET" in f.name:
                display_val = "***" if val else "''"
            else:
                display_val = repr(val)
            attrs.append(f"{f.name}={display_val}")
        return f"Settings({', '.join(attrs)})"

    def __str__(self) -> str:
        return self.__repr__()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached frozen Settings instance loaded from environment."""
    return Settings(
        FIRMS_MAP_KEY=os.getenv("FIRMS_MAP_KEY", ""),
        LLM_CHAIN=os.getenv(
            "LLM_CHAIN",
            "groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant,ollama:qwen2.5:7b-instruct",
        ),
        LLM_PLANNER_MODEL=os.getenv("LLM_PLANNER_MODEL", "groq:llama-3.1-8b-instant"),
        LLM_BRIEFING_MODEL=os.getenv("LLM_BRIEFING_MODEL", "groq:llama-3.3-70b-versatile"),
        GROQ_API_KEY=os.getenv("GROQ_API_KEY", ""),
        GROQ_BASE_URL=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        LLM_DAILY_TOKEN_BUDGET=int(os.getenv("LLM_DAILY_TOKEN_BUDGET", "100000")),
        LLM_TIMEOUT_S=int(os.getenv("LLM_TIMEOUT_S", "20")),
        POLL_S=int(os.getenv("POLL_S", "60")),
        CACHE_DIR=os.getenv("CACHE_DIR", ".cache"),
        SIMULATE_API_FAILURE=os.getenv("SIMULATE_API_FAILURE", ""),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        API_PORT=int(os.getenv("API_PORT", "8000")),
        CORS_ORIGINS=os.getenv("CORS_ORIGINS", "http://localhost:5173"),
        HTTP_TIMEOUT_S=int(os.getenv("HTTP_TIMEOUT_S", "20")),
        HTTP_RETRIES=int(os.getenv("HTTP_RETRIES", "3")),
        WEATHER_TTL_S=int(os.getenv("WEATHER_TTL_S", "600")),
        FIRES_TTL_S=int(os.getenv("FIRES_TTL_S", "900")),
        GRID_RES_M=int(os.getenv("GRID_RES_M", "90")),
        MAX_GRID_CELLS=int(os.getenv("MAX_GRID_CELLS", "400")),
        HORIZON_MIN=int(os.getenv("HORIZON_MIN", "720")),
    )
