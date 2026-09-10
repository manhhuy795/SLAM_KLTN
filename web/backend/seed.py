import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal

from app.models.operator import Operator
from app.models.robot import Robot
from app.models.location import Location
from app.models.product import Product
from app.models.line_segment import LineSegment
from app.models.landmark import Landmark
from app.models.robot_status import RobotStatus


def get_by_code(
    db: Session,
    model,
    field_name: str,
    value: str,
):
    field = getattr(model, field_name)

    return db.scalar(
        select(model).where(field == value)
    )


def seed_operators(db: Session):
    operator = get_by_code(
        db,
        Operator,
        "operator_code",
        "OPR-0001",
    )

    if operator is None:
        operator = Operator(
            operator_code="OPR-0001",
            full_name="Nhân viên vận hành",
            role="OPERATOR",
            is_active=True,
        )

        db.add(operator)

    print("✓ Operators")


def seed_robots(db: Session):
    robots = [
        {
            "robot_code": "AMR-01",
            "name": "AMR 01",
            "robot_type": "AMR",
            "model": "Warehouse AMR",
        },
        {
            "robot_code": "LINE-01",
            "name": "Line Robot 01",
            "robot_type": "LINE",
            "model": "Line Following AGV",
        },
    ]

    for data in robots:
        robot = get_by_code(
            db,
            Robot,
            "robot_code",
            data["robot_code"],
        )

        if robot is None:
            db.add(
                Robot(
                    **data,
                    is_active=True,
                )
            )

    db.flush()

    print("✓ Robots")


def seed_locations(db: Session):
    locations = [
        {
            "code": "HOME-01",
            "name": "HOME",
            "location_type": "HOME",
            "x": 1.0,
            "y": 1.0,
            "yaw": 0.0,
        },
        {
            "code": "RACK-A01",
            "name": "Kệ A01",
            "location_type": "RACK",
            "x": 3.0,
            "y": 2.0,
            "yaw": 0.0,
        },
        {
            "code": "RACK-A02",
            "name": "Kệ A02",
            "location_type": "RACK",
            "x": 3.0,
            "y": 4.0,
            "yaw": 0.0,
        },
        {
            "code": "RACK-B01",
            "name": "Kệ B01",
            "location_type": "RACK",
            "x": 6.0,
            "y": 2.0,
            "yaw": 0.0,
        },
        {
            "code": "PICK-01",
            "name": "Điểm nhận hàng 01",
            "location_type": "PICKUP",
            "x": 2.0,
            "y": 3.0,
            "yaw": 0.0,
        },
        {
            "code": "DEL-01",
            "name": "Điểm giao hàng 01",
            "location_type": "DELIVERY",
            "x": 8.0,
            "y": 2.0,
            "yaw": 0.0,
        },
        {
            "code": "DEL-02",
            "name": "Điểm giao hàng 02",
            "location_type": "DELIVERY",
            "x": 8.0,
            "y": 5.0,
            "yaw": 0.0,
        },
        {
            "code": "CHARGE-01",
            "name": "Trạm sạc 01",
            "location_type": "CHARGING",
            "x": 1.0,
            "y": 6.0,
            "yaw": 0.0,
        },
    ]

    for data in locations:
        location = get_by_code(
            db,
            Location,
            "code",
            data["code"],
        )

        if location is None:
            db.add(
                Location(
                    **data,
                    is_active=True,
                )
            )

    db.flush()

    print("✓ Locations")


def seed_products(db: Session):
    rack_a01 = get_by_code(
        db,
        Location,
        "code",
        "RACK-A01",
    )

    rack_a02 = get_by_code(
        db,
        Location,
        "code",
        "RACK-A02",
    )

    rack_b01 = get_by_code(
        db,
        Location,
        "code",
        "RACK-B01",
    )

    products = [
        {
            "product_code": "P-001",
            "name": "Bộ cảm biến",
            "default_rack_id": rack_a01.id,
        },
        {
            "product_code": "P-002",
            "name": "Cụm động cơ",
            "default_rack_id": rack_a02.id,
        },
        {
            "product_code": "P-003",
            "name": "Hộp linh kiện",
            "default_rack_id": rack_b01.id,
        },
    ]

    for data in products:
        product = get_by_code(
            db,
            Product,
            "product_code",
            data["product_code"],
        )

        if product is None:
            db.add(
                Product(
                    product_code=data["product_code"],
                    name=data["name"],
                    image_path=None,
                    status="AVAILABLE",
                    default_rack_id=data["default_rack_id"],
                )
            )

    db.flush()

    print("✓ Products")


def seed_line_segments(db: Session):
    home = get_by_code(
        db,
        Location,
        "code",
        "HOME-01",
    )

    pickup = get_by_code(
        db,
        Location,
        "code",
        "PICK-01",
    )

    delivery_01 = get_by_code(
        db,
        Location,
        "code",
        "DEL-01",
    )

    delivery_02 = get_by_code(
        db,
        Location,
        "code",
        "DEL-02",
    )

    segments = [
        {
            "segment_code": "SEG-01",
            "start_location_id": home.id,
            "end_location_id": pickup.id,
            "length_m": 3.0,
            "polyline_json": json.dumps(
                [
                    [1.0, 1.0],
                    [1.0, 3.0],
                    [2.0, 3.0],
                ]
            ),
        },
        {
            "segment_code": "SEG-02",
            "start_location_id": pickup.id,
            "end_location_id": delivery_01.id,
            "length_m": 6.5,
            "polyline_json": json.dumps(
                [
                    [2.0, 3.0],
                    [5.0, 3.0],
                    [5.0, 2.0],
                    [8.0, 2.0],
                ]
            ),
        },
        {
            "segment_code": "SEG-03",
            "start_location_id": pickup.id,
            "end_location_id": delivery_02.id,
            "length_m": 7.0,
            "polyline_json": json.dumps(
                [
                    [2.0, 3.0],
                    [5.0, 3.0],
                    [5.0, 5.0],
                    [8.0, 5.0],
                ]
            ),
        },
    ]

    for data in segments:
        segment = get_by_code(
            db,
            LineSegment,
            "segment_code",
            data["segment_code"],
        )

        if segment is None:
            db.add(
                LineSegment(
                    **data,
                    is_active=True,
                )
            )

    db.flush()

    print("✓ Line segments")


def seed_landmarks(db: Session):
    segment_01 = get_by_code(
        db,
        LineSegment,
        "segment_code",
        "SEG-01",
    )

    segment_02 = get_by_code(
        db,
        LineSegment,
        "segment_code",
        "SEG-02",
    )

    segment_03 = get_by_code(
        db,
        LineSegment,
        "segment_code",
        "SEG-03",
    )

    landmarks = [
        {
            "landmark_code": "TAG-001",
            "segment_id": segment_01.id,
            "x": 1.0,
            "y": 2.0,
            "yaw": 0.0,
        },
        {
            "landmark_code": "TAG-002",
            "segment_id": segment_02.id,
            "x": 5.0,
            "y": 3.0,
            "yaw": 0.0,
        },
        {
            "landmark_code": "TAG-003",
            "segment_id": segment_03.id,
            "x": 5.0,
            "y": 5.0,
            "yaw": 0.0,
        },
    ]

    for data in landmarks:
        landmark = get_by_code(
            db,
            Landmark,
            "landmark_code",
            data["landmark_code"],
        )

        if landmark is None:
            db.add(
                Landmark(
                    landmark_code=data["landmark_code"],
                    landmark_type="APRILTAG",
                    segment_id=data["segment_id"],
                    x=data["x"],
                    y=data["y"],
                    yaw=data["yaw"],
                    is_active=True,
                )
            )

    db.flush()

    print("✓ Landmarks")


def seed_robot_status(db: Session):
    robots = db.scalars(
        select(Robot)
    ).all()

    for robot in robots:
        status = db.get(
            RobotStatus,
            robot.id,
        )

        if status is None:
            db.add(
                RobotStatus(
                    robot_id=robot.id,
                    online=False,
                    state="UNKNOWN",
                    battery_percent=None,
                    voltage=None,
                    x=None,
                    y=None,
                    yaw=None,
                    line_segment_id=None,
                    localization_quality=None,
                )
            )

    print("✓ Robot status")


def seed_database():
    db = SessionLocal()

    try:
        print("\n===== SEED WRMS DATABASE =====\n")

        seed_operators(db)
        seed_robots(db)
        seed_locations(db)
        seed_products(db)
        seed_line_segments(db)
        seed_landmarks(db)
        seed_robot_status(db)

        db.commit()

        print("\nDatabase seeded successfully.")

    except Exception as exc:
        db.rollback()

        print("\nSeed failed:")
        print(exc)

        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()