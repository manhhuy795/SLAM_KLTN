from app.models.robot_command import RobotCommand


def add_robot_command(
    db,
    robot_id: int,
    command: str,
    task_id: int | None = None,
):
    robot_command = RobotCommand(
        robot_id=robot_id,
        task_id=task_id,
        command=command,
        status="PENDING",
    )
    db.add(robot_command)
    db.flush()
    return robot_command


def build_robot_command_response(command: RobotCommand):
    return {
        "id": command.id,
        "robot_id": command.robot_id,
        "task_id": command.task_id,
        "command": command.command,
        "status": command.status,
        "failure_reason": command.failure_reason,
        "created_at": command.created_at,
        "acknowledged_at": command.acknowledged_at,
    }
