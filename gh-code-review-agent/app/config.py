import os
from functools import lru_cache
import os
from dotenv import load_dotenv

from pydantic_settings import BaseSettings

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))

# Load the .env file
dotenv_path = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path)

class APISettings(BaseSettings):
    # DEBUG = True
    APP_NAME:str = "gh-code-review-agent"
    JWT_ALGORITHM:str = os.getenv("JWT_ALGORITHM","")
    
    SYSTEM_IDENTITY:str = os.getenv("SYSTEM_IDENTITY","")
    SECRET_KEY:str = os.getenv("SECRET_KEY","")
    BEARER_SYSTEM_JWT:str =os.getenv("BEARER_SYSTEM_JWT","")
    OLLAMA_LOCAL_URL: str = os.getenv("OLLAMA_LOCAL_URL","")

    # Redis Credentials
    REDIS_URL: str = os.getenv("REDIS_URL","")
    #COMMON
    DATABASE_URL:str = os.getenv("DATABASE_URL","")
    CELERY_BROKER_URL:str = os.getenv("REDIS_URL","")
    CELERY_RESULT_BACKEND:str = os.getenv("REDIS_URL","")

    #github
    DEFAULT_GITHUB_TOKEN:str =""
    GITHUB_API_VERSION:str = os.getenv("GITHUB_API_VERSION","2022-11-28")


    AGNO_MODEL: str = "llama3.2:latest"             # pick any local Ollama model you pulled
    OLLAMA_HOST: str = "http://localhost:11434" # in Docker; use "http://localhost:11434" when running locally

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return APISettings()
