from pathlib import Path
from functools import lru_cache
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


class Settings(BaseModel):
    api_key: str = Field(default='', repr=False)
    base_url: str = 'https://api.deepseek.com'
    model: str = 'deepseek-v4-pro'
    max_steps: int = Field(default=8, ge=1, le=30)
    max_tools: int = Field(default=10, ge=1, le=30)
    run_timeout: float = Field(default=90, gt=0)
    model_timeout: float = Field(default=40, gt=0)
    tool_timeout: float = Field(default=10, gt=0)


@lru_cache
def settings():
    return Settings(api_key=os.getenv('DEEPSEEK_API_KEY', ''),
        base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
        model=os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-pro'),
        max_steps=int(os.getenv('MAX_STEPS', '8')),
        max_tools=int(os.getenv('MAX_TOOL_CALLS', '10')),
        run_timeout=float(os.getenv('RUN_TIMEOUT_SECONDS', '90')),
        model_timeout=float(os.getenv('MODEL_TIMEOUT_SECONDS', '40')),
        tool_timeout=float(os.getenv('TOOL_TIMEOUT_SECONDS', '10')))
