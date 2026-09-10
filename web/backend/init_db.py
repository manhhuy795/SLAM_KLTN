from app.db.base import Base
from app.db.database import engine

from app.models.operator import Operator
from app.models.robot import Robot
from app.models.location import Location
from app.models.product import Product
from app.models.line_segment import LineSegment
from app.models.robot_status import RobotStatus
from app.models.robot_command import RobotCommand
from app.models.landmark import Landmark

from app.models.task import Task
from app.models.task_proof import TaskProof
from app.models.alert import Alert
from app.models.event_log import EventLog


def init_database():
    Base.metadata.create_all(bind=engine)

    print("Database initialized successfully.")


if __name__ == "__main__":
    init_database()
