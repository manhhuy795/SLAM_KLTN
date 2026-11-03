import { SVG_LEFT, SVG_TOP, SVG_WIDTH, SVG_HEIGHT, toSvgX, toSvgY, canPlaceOnFallbackMap } from './fallbackCoordinates';
import RestrictedZone from './RestrictedZones';
import LocationsLayer from './LocationsLayer';

const TERMINAL_TASK_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
]);


export default function FallbackWarehouseMap({ locations, robots, tasks }) {
  const activeTasks = tasks.filter(
    (task) =>
      !TERMINAL_TASK_STATUSES.has(
        task.status
      )
  );


  const positionedRobots = robots.filter(canPlaceOnFallbackMap);
  const unpositionedCount = robots.filter(robot => robot.robot_type !== 'LINE' && !canPlaceOnFallbackMap(robot)).length;
  const uncalibratedAgvs = robots.filter(robot => robot.robot_type === 'LINE');

  return (
      <div className="map-canvas warehouse-map-schematic">
        <svg
          viewBox="0 0 640 340"
          role="img"
          aria-label="Bản đồ tổng quan kho thử nghiệm"
        >
          <defs>
            <pattern
              id="grid-pattern"
              width="20"
              height="20"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 20 0 L 0 0 0 20"
                fill="none"
                stroke="#12151B"
                strokeWidth="0.8"
              />
            </pattern>


            <pattern
              id="hazard-pattern"
              width="8"
              height="8"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line
                x1="0"
                y1="0"
                x2="0"
                y2="8"
                stroke="#F59E0B"
                strokeWidth="1.8"
                opacity="0.35"
              />
            </pattern>
          </defs>


          {/* Nền */}
          <rect
            width="640"
            height="340"
            fill="url(#grid-pattern)"
          />

          <rect
            x={SVG_LEFT}
            y={SVG_TOP}
            width={SVG_WIDTH}
            height={SVG_HEIGHT}
            fill="none"
            stroke="#1E2229"
            strokeWidth="1.5"
          />


          {/* Tọa độ */}
          <MapCoordinates />


          {/* Khu vực hạn chế:
              đây là geometry của testbed,
              không phải location point trong DB.
          */}
          <RestrictedZone />


          {/* Location thật từ DB */}
          <LocationsLayer locations={locations} activeTasks={activeTasks} />


          {/* Robot chỉ render khi có tọa độ thật */}
          {positionedRobots.map((robot) => (
            <RobotMarker
              key={robot.id}
              robot={robot}
              task={findRobotTask(
                robot.id,
                activeTasks
              )}
            />
          ))}
        </svg>


        {(unpositionedCount > 0 || uncalibratedAgvs.length > 0) && (
          <div className="map-telemetry-note" role="status">
            {unpositionedCount > 0 && <div>{unpositionedCount} robot chưa có dữ liệu vị trí</div>}
            {uncalibratedAgvs.map(robot => (
              <div key={robot.id}>{robot.robot_code}: POSITION_UNKNOWN / UNCALIBRATED</div>
            ))}
          </div>
        )}
      </div>

  );
}

function MapCoordinates() {
  return (
    <>
      <MapText
        x="20"
        y="22"
        text="[0.0, 0.0]"
      />

      <MapText
        x="557"
        y="22"
        text="[12.0m, 0.0]"
      />

      <MapText
        x="20"
        y="314"
        text="[0.0, 8.0m]"
      />

      <MapText
        x="545"
        y="314"
        text="[12.0m, 8.0m]"
      />
    </>
  );
}


function MapText({
  x,
  y,
  text,
}) {
  return (
    <text
      x={x}
      y={y}
      fill="#94A3B8"
      fontFamily="JetBrains Mono, monospace"
      fontSize="7"
    >
      {text}
    </text>
  );
}


// The fallback schematic has no map identity to validate AGV-local odometry against.
function RobotMarker({
  robot,
  task,
}) {
  const status = robot.status;

  const x = toSvgX(status.x);
  const y = toSvgY(status.y);

  const online =
    status.online ?? false;

  const isLine =
    robot.robot_type === 'LINE';

  const color =
    isLine
      ? '#8BA888'
      : '#FF7300';


  const yawDegrees =
    status.yaw === null ||
    status.yaw === undefined
      ? 0
      : status.yaw *
        (180 / Math.PI);


  return (
    <g
      transform={`translate(${x} ${y})`}
      opacity={online ? 1 : 0.5}
    >
      {isLine ? (
        <polygon
          points="0,-8 8,0 0,8 -8,0"
          fill={color}
          stroke="#000000"
          strokeWidth="1.2"
        />
      ) : (
        <>
          <circle
            cx="0"
            cy="0"
            r="10"
            fill={color}
            stroke="#FFFFFF"
            strokeWidth="1.1"
          />

          <polygon
            points="-3,-5 6,0 -3,5"
            fill="#000000"
            transform={
              `rotate(${yawDegrees})`
            }
          />

          <circle
            cx="0"
            cy="0"
            r="15"
            fill="none"
            stroke={color}
            strokeDasharray="2 2"
            strokeWidth="0.8"
          />
        </>
      )}


      <RobotLabel
        robot={robot}
        task={task}
        color={color}
        right={isLine}
      />
    </g>
  );
}


function RobotLabel({
  robot,
  task,
  color,
  right,
}) {
  const x =
    right
      ? 13
      : -82;

  const textX =
    x + 6;


  return (
    <>
      <rect
        x={x}
        y="-15"
        width="68"
        height="31"
        rx="2"
        fill="#08090C"
        stroke={color}
        strokeWidth="0.8"
      />


      <text
        x={textX}
        y="-10"
        fill={color}
        fontFamily="Inter, Arial, sans-serif"
        fontSize="7.5"
        fontWeight="700"
        dominantBaseline="hanging"
      >
        {robot.robot_code}
      </text>


      <text
        x={textX}
        y="2"
        fill="#CBD5E1"
        fontFamily="JetBrains Mono, monospace"
        fontSize="6"
        dominantBaseline="hanging"
      >
        {task
          ? task.task_code
          : 'Không có task'}
      </text>
    </>
  );
}


function findRobotTask(
  robotId,
  tasks
) {
  return tasks.find(
    (task) =>
      task.robot_id === robotId
  );
}




