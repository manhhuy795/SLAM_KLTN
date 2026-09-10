from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder


class ConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)

    async def broadcast(self, event_type: str, data):
        message = jsonable_encoder({
            "type": event_type,
            "data": data,
        })

        disconnected = []

        for websocket in list(self.connections):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)


manager = ConnectionManager()


def queue_broadcast(background_tasks, event_type: str, data):
    background_tasks.add_task(
        manager.broadcast,
        event_type,
        data,
    )


def event_data(event):
    return {
        "id": event.id,
        "robot_id": event.robot_id,
        "robot_code": getattr(event, "robot_code", None),
        "task_id": event.task_id,
        "task_code": getattr(event, "task_code", None),
        "operator_id": event.operator_id,
        "event_type": event.event_type,
        "source": event.source,
        "message": event.message,
        "metadata_json": event.metadata_json,
        "created_at": event.created_at,
    }


def queue_event(background_tasks, event):
    queue_broadcast(
        background_tasks,
        "EVENT_CREATED",
        event_data(event),
    )
