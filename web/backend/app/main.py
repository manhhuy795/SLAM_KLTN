import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.robots import router as robots_router
from app.api.routes.agv import router as agv_router
from app.api.routes.commands import router as commands_router
from app.api.routes.locations import router as locations_router
from app.api.routes.products import router as products_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.history import router as history_router
from app.api.routes.operators import router as operators_router
from app.api.routes.ros import router as ros_router
from app.services.realtime import manager
from app.api.routes.maps import router as maps_router
from app.db.database import engine
from app.models.saved_map import SavedMap
from app.models.planning_layer import PlanningLayer
from app.api.routes.planning import router as planning_router


@asynccontextmanager
async def lifespan(app):
    SavedMap.__table__.create(bind=engine, checkfirst=True)
    PlanningLayer.__table__.create(bind=engine, checkfirst=True)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="WRMS API",
    description="Warehouse Robot Management System API",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.192.134:5173",
        *[origin.strip() for origin in os.getenv("WRMS_CORS_ORIGINS", "").split(",")
          if origin.strip()],
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

app.include_router(maps_router, prefix="/api")

app.include_router(planning_router, prefix="/api")

from app.api.routes.map_session import router as map_session_router
app.include_router(map_session_router, prefix="/api")

app.include_router(agv_router, prefix="/api")
