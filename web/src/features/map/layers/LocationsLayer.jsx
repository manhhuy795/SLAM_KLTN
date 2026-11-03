import { toSvgX, toSvgY } from './fallbackCoordinates';

export default function LocationsLayer({ locations, activeTasks }) {
  return locations.map((location) => (
    <MapLocation key={location.id} location={location} task={findTaskAtLocation(location.id, activeTasks)} />
  ));
}

function MapLocation({
  location,
  task,
}) {
  const x = toSvgX(location.x);
  const y = toSvgY(location.y);

  const config =
    getLocationConfig(
      location.location_type
    );


  const width =
    location.location_type === 'RACK'
      ? 72
      : 92;

  const height =
    location.location_type === 'RACK'
      ? 34
      : 42;


  return (
    <g
      transform={
        `translate(${
          x - width / 2
        } ${
          y - height / 2
        })`
      }
      opacity={
        location.is_active
          ? 1
          : 0.45
      }
    >
      <rect
        width={width}
        height={height}
        fill="#0E1014"
        stroke={
          task
            ? '#FF7300'
            : config.stroke
        }
        strokeWidth={
          task
            ? 1.4
            : 1
        }
      />


      <text
        x="7"
        y="7"
        fill={config.color}
        fontFamily="Inter, Arial, sans-serif"
        fontSize="7.5"
        fontWeight="700"
        dominantBaseline="hanging"
      >
        {location.name}
      </text>


      <text
        x="7"
        y="20"
        fill="#94A3B8"
        fontFamily="JetBrains Mono, monospace"
        fontSize="6.3"
        dominantBaseline="hanging"
      >
        {location.code}
      </text>


      {task && (
        <>
          <rect
            x={width - 39}
            y={height - 14}
            width="35"
            height="10"
            fill="#08090C"
            stroke="#FF7300"
            strokeWidth="0.6"
          />

          <text
            x={width - 36}
            y={height - 12}
            fill="#FF7300"
            fontFamily="JetBrains Mono, monospace"
            fontSize="5.7"
            fontWeight="700"
            dominantBaseline="hanging"
          >
            {task.task_code}
          </text>
        </>
      )}
    </g>
  );
}


function getLocationConfig(type) {
  const configs = {
    HOME: {
      color: '#FF7300',
      stroke: '#FF7300',
    },

    RACK: {
      color: '#F1F5F9',
      stroke: '#2A313D',
    },

    PICKUP: {
      color: '#8BA888',
      stroke: '#8BA888',
    },

    DELIVERY: {
      color: '#8BA888',
      stroke: '#8BA888',
    },

    CHARGING: {
      color: '#8BA888',
      stroke: '#8BA888',
    },
  };


  return (
    configs[type] ?? {
      color: '#F1F5F9',
      stroke: '#2A313D',
    }
  );
}


function findTaskAtLocation(
  locationId,
  tasks
) {
  return tasks.find(
    (task) =>
      task.pickup_location_id ===
        locationId ||
      task.dropoff_location_id ===
        locationId
  );
}


