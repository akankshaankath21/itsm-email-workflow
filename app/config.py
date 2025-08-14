from typing import Optional
from pydantic_settings import BaseSettings
from app.prompts import EMAIL_ANALYSIS_PROMPT

class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # App Configuration
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_name: str = "ITSM Workflow Automation"
    app_version: str = "1.0.0"
    
    # Database Configuration
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/itsm_workflow"
    
    # LLM Configuration
    llm_use_stub: bool = True
    llm_system_prompt: str = EMAIL_ANALYSIS_PROMPT
    
    # Azure OpenAI Configuration
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: str = "gpt-4"
    azure_openai_api_version: str = "2024-02-15-preview"
    
    # Gmail Configuration
    gmail_credentials_dir: str = "./credentials"
    gmail_default_polling_interval: int = 30
    gmail_max_polling_interval: int = 3600
    gmail_min_polling_interval: int = 5
    
    # Workflow Configuration
    max_workflow_execution_time: int = 300  # 5 minutes
    max_emails_per_workflow: int = 50
    
    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Global settings instance
settings = Settings()