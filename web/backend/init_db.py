from app.db.base import Base
from app.db.database import engine

from app.models.operator import Operator
from app.models.robot import Robot
from app.models.location import Location
from app.models.saved_map import SavedMap
from app.models.planning_layer import PlanningLayer
from app.models.product import Product
from app.models.line_segment import LineSegment
from app.models.robot_status import RobotStatus
from app.models.robot_command import RobotCommand
from app.models.landmark import Landmark

from app.models.task import Task
from app.models.task_proof import TaskProof
from app.models.alert import Alert
from app.models.event_log import EventLog
from app.models.agv_mission import AgvMission, AgvMissionCommand
from app.models.agv_cargo_evidence import AgvCargoEvidence
from app.models.agv_vision import AgvClassRackPolicy, AgvVisionJob, AgvVisionCapture


def migrate_nullable_task_fields(path):
    """Preserve the existing SQLite schema while allowing unassigned LINE tasks."""
    import re
    import sqlite3
    from contextlib import closing
    from datetime import datetime
    from pathlib import Path

    path = Path(path)
    if not path.exists():
        return None
    with closing(sqlite3.connect(path)) as db:
        columns = {row[1]: row[3] for row in db.execute("PRAGMA table_info(tasks)")}
        if not columns or (columns.get("product_id"), columns.get("dropoff_location_id")) == (0, 0):
            return None
        if (columns.get("product_id"), columns.get("dropoff_location_id")) != (1, 1):
            raise RuntimeError("Unexpected tasks schema; migration stopped")
        ddl = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()[0]
        new_ddl, replacements = re.subn(
            r"(?m)^(\s*(?:product_id|dropoff_location_id)\s+INTEGER) NOT NULL,",
            r"\1,", ddl)
        if replacements != 2:
            raise RuntimeError("Unexpected tasks DDL; migration stopped")
        new_ddl = new_ddl.replace("CREATE TABLE tasks (", "CREATE TABLE tasks__migrating (", 1)
        if new_ddl == ddl:
            raise RuntimeError("Unexpected tasks table name; migration stopped")
        dependent_sql = [row[0] for row in db.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='tasks' AND type IN ('index','trigger') AND sql IS NOT NULL")]

        backup = path.with_name(path.name + ".backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        with closing(sqlite3.connect(backup)) as destination:
            db.backup(destination)
        with closing(sqlite3.connect(backup)) as saved:
            if saved.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite backup failed integrity check")

        db.execute("PRAGMA foreign_keys=OFF")
        try:
            db.execute("BEGIN IMMEDIATE")
            before = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            db.execute(new_ddl)
            db.execute("INSERT INTO tasks__migrating SELECT * FROM tasks")
            db.execute("DROP TABLE tasks")
            db.execute("ALTER TABLE tasks__migrating RENAME TO tasks")
            for statement in dependent_sql:
                db.execute(statement)
            if db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] != before:
                raise RuntimeError("Task row count changed during migration")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Foreign key violations after tasks migration")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite integrity check failed after tasks migration")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("PRAGMA foreign_keys=ON")
        return backup


def init_database():
    if engine.dialect.name == "sqlite" and engine.url.database:
        migrate_nullable_task_fields(engine.url.database)
    Base.metadata.create_all(bind=engine)

    print("Database initialized successfully.")


if __name__ == "__main__":
    init_database()
