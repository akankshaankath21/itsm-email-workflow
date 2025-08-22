
from typing import Optional
from pydantic_settings import BaseSettings
from app.prompts import EMAIL_ANALYSIS_PROMPT

class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_name: str = "ITSM Workflow Automation Platform"
    app_version: str = "2.0.0"

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/itsm_workflow"

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600
    
    llm_use_stub: bool = False
    llm_system_prompt: str = EMAIL_ANALYSIS_PROMPT

    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: str = "gpt-4"
    azure_openai_api_version: str = "2024-02-15-preview"

    llm_temperature: float = 0.0
    llm_max_tokens: int = 500
    llm_timeout_seconds: int = 30

    gmail_credentials_dir: str = "./credentials"
    gmail_default_polling_interval: int = 30
    gmail_max_polling_interval: int = 3600
    gmail_min_polling_interval: int = 5
    gmail_default_max_results: int = 10
    gmail_max_results_limit: int = 100

    gmail_oauth_port: int = 8080
    gmail_oauth_redirect_uri: str = "http://localhost:8080"

    max_workflow_execution_time: int = 300
    max_emails_per_workflow: int = 50
    workflow_retry_attempts: int = 3
    workflow_retry_delay: int = 5

    max_workflow_nodes: int = 20
    max_workflow_edges: int = 50
    max_concurrent_workflow_instances: int = 10
    workflow_instance_timeout: int = 1800

    dag_max_execution_depth: int = 10
    dag_node_timeout: int = 300
    dag_data_size_limit: int = 10485760

    enable_execution_monitoring: bool = True
    execution_log_level: str = "INFO"
    max_execution_history: int = 1000

    api_rate_limit: int = 1000
    max_concurrent_requests: int = 100
    request_timeout: int = 60

    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file_path: Optional[str] = None
    log_max_size: int = 10485760
    log_backup_count: int = 5

    enable_api_key_auth: bool = False
    api_key_header: str = "X-API-Key"
    allowed_api_keys: list[str] = []

    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    environment: str = "development"
    debug_mode: bool = True
    enable_swagger_ui: bool = True
    enable_redoc: bool = True

    servicenow_instance_url: Optional[str] = None
    servicenow_username: Optional[str] = None
    servicenow_password: Optional[str] = None

    jira_server_url: Optional[str] = None
    jira_username: Optional[str] = None
    jira_api_token: Optional[str] = None

    slack_bot_token: Optional[str] = None
    slack_signing_secret: Optional[str] = None

    def validate_azure_openai_config(self) -> bool:
        if self.llm_use_stub:
            return True
        return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
    
    def validate_gmail_config(self) -> bool:
        import os
        return os.path.exists(self.gmail_credentials_dir)
    
    def get_effective_log_level(self) -> str:
        if self.environment == "production":
            return "WARNING"
        elif self.environment == "staging":
            return "INFO"
        else:
            return self.log_level
    
    def get_database_config(self) -> dict:
        return {
            "url": self.database_url,
            "pool_size": self.db_pool_size,
            "max_overflow": self.db_max_overflow,
            "pool_timeout": self.db_pool_timeout,
            "pool_recycle": self.db_pool_recycle,
            "echo": self.debug_mode and self.environment != "production"
        }
    
    def get_cors_config(self) -> dict:
        return {
            "allow_origins": self.cors_origins,
            "allow_credentials": self.cors_credentials,
            "allow_methods": self.cors_methods,
            "allow_headers": self.cors_headers
        }
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()

def validate_configuration():
    issues = []
    
    if not settings.validate_azure_openai_config():
        issues.append("Azure OpenAI configuration incomplete (missing API key or endpoint)")
    
    if not settings.validate_gmail_config():
        issues.append(f"Gmail credentials directory not found: {settings.gmail_credentials_dir}")
    
    if settings.environment == "production" and settings.debug_mode:
        issues.append("Debug mode should be disabled in production")
    
    if settings.cors_origins == ["*"] and settings.environment == "production":
        issues.append("CORS origins should be restricted in production")
    
    return issues