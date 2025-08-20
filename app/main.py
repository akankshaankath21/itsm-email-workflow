
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.api.routes import router as core_router
from app.api.dynamic_workflow_routes import workflow_router
from app.db import init_models
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format=settings.log_format
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ITSM Workflow Automation API...")
    try:
        await init_models()
        logger.info("Database initialized successfully")
        logger.info("System ready for both static and dynamic workflows")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        logger.info("Shutting down ITSM Workflow Automation API...")

def create_app() -> FastAPI:
    
    app = FastAPI(
        title=settings.app_name,
        description="ITSM Workflow Automation Platform",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )
    

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "healthy",
            "version": settings.app_version,
            "app": settings.app_name,
            "workflow_support": "static_and_dynamic"
        }
    

    app.include_router(
        core_router, 
        prefix="/api",

    )
    
    app.include_router(
        workflow_router, 
        prefix="/api",

    )
    
    @app.get("/")
    async def root():
        return {
            "message": f"Welcome to {settings.app_name}",
            "version": settings.app_version,
            "documentation": {
                "swagger_ui": "/docs",
                "redoc": "/redoc"
            },
            "api_structure": {
                "core_api": "/api",
                "dynamic_workflows": "/api"
            },
            "demo_flow": {
                "step_1": "Create Gmail node: POST /api/nodes/gmail",
                "step_2": "Start monitoring: POST /api/nodes/gmail/{id}/start", 
                "step_3": "Test classifier: POST /api/nodes/classifier/execute",
                "step_4": "Run static workflow: POST /api/workflows/static/gmail-to-classifier/{id}",
                "step_5": "Create dynamic template: POST /api/templates",
                "step_6": "Add nodes to template: POST /api/templates/{id}/nodes",
                "step_7": "Connect nodes: POST /api/templates/{id}/edges",
                "step_8": "Execute dynamic workflow: POST /api/templates/{id}/execute",
                "step_9": "Monitor execution: GET /api/instances/{id}/status"
            },
            "features": [
                "Gmail Email Monitoring (OAuth)",
                "AI Email Classification (Azure OpenAI)", 
                "Static Workflow Automation (Direct Service Calls)",
                "Dynamic Workflow Builder (Template-based DAG)",
                "Real-time Execution Monitoring",
                "Service Integration Architecture",
                "ITSM Process Automation Ready"
            ],
            "architecture": {
                "pattern": "MVC (Model-View-Controller)",
                "workflow_engine": "DAG-based execution",
                "database": "PostgreSQL with SQLAlchemy",
                "ai_integration": "Azure OpenAI",
                "email_integration": "Gmail API with OAuth2"
            }
        }
    
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        log_level=settings.log_level.lower()
    )