from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.robots import router as robots_router
from app.api.routes.commands import router as commands_router
from app.api.routes.locations import router as locations_router
from app.api.routes.products import router as products_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.history import router as history_router
from app.api.routes.operators import router as operators_router
from app.api.routes.ros import router as ros_router
from app.services.realtime import manager

app = FastAPI(
    title="WRMS API",
    description="Warehouse Robot Management System API",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"^https://[a-zA-Z0-9-]+\.trycloudflare\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "WRMS API",
        "status": "running",
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


app.include_router(
    commands_router,
    prefix="/api",
)

app.include_router(
    robots_router,
    prefix="/api",
)

app.include_router(
    locations_router,
    prefix="/api",
)

app.include_router(
    products_router,
    prefix="/api",
)

app.include_router(
    tasks_router,
    prefix="/api",
)

app.include_router(
    alerts_router,
    prefix="/api",
)

app.include_router(
    history_router,
    prefix="/api",
)

app.include_router(
    operators_router,
    prefix="/api",
)

app.include_router(
    ros_router,
    prefix="/api",
)
