import time
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

# Import your new Zalo Channel
from agentic_tools.channels.zalo import ZaloOAChannel

# ============================================================
# Domain Imports
# ============================================================
from agentic_models.router import AgentRouter, build_messages
from agentic_tools.tools import (
    AVAILABLE_TOOLS,
    get_date,
    get_current_weather,
    manage_leo_segment,
    activate_channel,
)
from main_configs import (
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    CORS_ALLOW_ORIGINS,
    MAIN_APP_DESCRIPTION,
    MAIN_APP_TITLE,
    MAIN_APP_VERSION,
)

# ============================================================
# Logging
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LEO Activation API")


# ============================================================
# App Factory
# ============================================================
def create_app() -> FastAPI:
    app = FastAPI(
        title=MAIN_APP_TITLE,
        description=MAIN_APP_DESCRIPTION,
        version=MAIN_APP_VERSION,
    )

    # --------------------
    # CORS
    # --------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=CORS_ALLOW_CREDENTIALS,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )

    # --------------------
    # Static & Templates (safe for test env)
    # --------------------
    base_dir = Path(__file__).resolve().parent
    resources_dir = base_dir / "agentic_resources"
    templates_dir = resources_dir / "templates"

    if resources_dir.exists():
        app.mount(
            "/resources",
            StaticFiles(directory=resources_dir),
            name="resources",
        )

    if templates_dir.exists():
        app.state.templates = Jinja2Templates(directory=templates_dir)
    else:
        app.state.templates = None

    # --------------------
    # Health
    # --------------------
    @app.get("/ping")
    def ping():
        return {"status": "ok"}

    # --------------------
    # Root
    # --------------------
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if not request.app.state.templates:
            return HTMLResponse("<h1>LEO Activation API</h1>", status_code=200)

        ts = int(time.time())
        return request.app.state.templates.TemplateResponse(
            "test.html",
            {"request": request, "timestamp": ts},
        )

    # ========================================================
    # Agent Setup
    # ========================================================
    agent_router = AgentRouter(mode="auto")

    TOOLS = [
        get_date,
        get_current_weather,
        manage_leo_segment,
        activate_channel,
    ]

    TOOLS_MAP = AVAILABLE_TOOLS

    # ========================================================
    # Schemas (Pydantic v2–correct)
    # ========================================================
    class ChatRequest(BaseModel):
        prompt: str = Field(
            ...,
            description="User natural language query",
            json_schema_extra={
                "example": "Send a Zalo message to users active last week"
            },
        )

    class ToolCallDebug(BaseModel):
        name: str
        arguments: Dict[str, Any]

    class ToolResultDebug(BaseModel):
        name: str
        response: Any

    class DebugInfo(BaseModel):
        calls: List[ToolCallDebug]
        data: List[ToolResultDebug]

    class ChatResponse(BaseModel):
        answer: str
        debug: DebugInfo

    # ========================================================
    # Chat Endpoint
    # ========================================================
    @app.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(payload: ChatRequest):
        try:
            logger.info("Incoming prompt: %s", payload.prompt)

            messages = build_messages(payload.prompt)
            response = agent_router.handle_message(
                messages,
                tools=TOOLS,
                tools_map=TOOLS_MAP,
            )

            return ChatResponse(
                answer=response["answer"],
                debug=DebugInfo(
                    calls=[ToolCallDebug(**c)
                           for c in response["debug"]["calls"]],
                    data=[ToolResultDebug(**d)
                          for d in response["debug"]["data"]],
                ),
            )

        except Exception as e:
            logger.exception("Chat endpoint failed")
            raise HTTPException(status_code=500, detail=str(e))

    return app

# Define the request body schema
class ZaloTestRequest(BaseModel):
    segment_name: str
    message: Optional[str] = None
    kwargs: Optional[Dict[str, Any]] = {} 

test_router = APIRouter()

@test_router.post("/test/zalo-direct")
async def test_zalo_direct(request: ZaloTestRequest):
    """
    Directly calls the Zalo channel with full parameter support.
    """
    try:
        zalo_channel = ZaloOAChannel()
        
        # ✅ UPDATED: Passing **request.kwargs to the send function
        result = zalo_channel.send(
            recipient_segment=request.segment_name, 
            message=request.message,
            **request.kwargs 
        )
        
        return {
            "status": "completed",
            "mode": "direct_test",
            "channel_response": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# App instance (used by uvicorn & tests)
# ============================================================
app = create_app()
