import { useEffect, useMemo, useState } from "react";

import {
  cancelNavigation,
  getLocations,
  getMapSession,
  getNavigationStatus,
  getRosMap,
  sendNavigationGoal,
} from "../services/api";
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from "../services/realtime";
import { isWorldPointInMap } from "../services/slamMap";


const ACTIVE_STATES = new Set(["SENDING", "NAVIGATING"]);


export default function NavigationPanel() {
  const [mapSession,setMapSession]=useState(null);
  const [mode, setMode] = useState("LOCATION");
  const [locations, setLocations] = useState([]);
  const [selectedLocationId, setSelectedLocationId] = useState("");
  const [manualValues, setManualValues] = useState({
    x: "1.0",
    y: "0.0",
    yaw: "0.0",
  });
  const [map, setMap] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const activeLocations = useMemo(
    () => locations.filter((location) => location.is_active),
    [locations],
  );
  const selectedLocation = activeLocations.find(
    (location) => String(location.id) === selectedLocationId,
  ) ?? null;
  const values = mode === "LOCATION" && selectedLocation
    ? {
        x: String(selectedLocation.x),
        y: String(selectedLocation.y),
        yaw: String(selectedLocation.yaw),
      }
    : manualValues;
  const goal = {
    x: parseCoordinate(values.x),
    y: parseCoordinate(values.y),
    yaw: parseCoordinate(values.yaw),
  };
  const coordinatesValid = Object.values(goal).every(Number.isFinite);
  const insideMap = !map || !coordinatesValid
    || isWorldPointInMap(map, goal.x, goal.y);
  const active = ACTIVE_STATES.has(status?.state);
  const targetReady = mode === "MANUAL" || selectedLocation !== null;
  const validationMessage = !targetReady
    ? "Select an active location."
    : !coordinatesValid
      ? "Coordinates must be finite."
      : !insideMap
        ? "Goal is outside the current SLAM map."
        : null;
  const navigateDisabled = busy
    || active
    || (mapSession?.enabled && !mapSession.ready)
    || status?.nav2_online !== true
    || validationMessage !== null;

  async function load() {
    const [nextStatus, nextLocations, nextMap] = await Promise.all([
      getNavigationStatus(),
      getLocations(),
      getRosMap(),
    ]);
    setStatus(nextStatus);
    setLocations(nextLocations);
    setMap(nextMap);
    setSelectedLocationId((current) => (
      nextLocations.some(
        (location) => location.is_active && String(location.id) === current,
      ) ? current : ""
    ));
  }

  useEffect(() => {
    getMapSession().then(setMapSession).catch(()=>{});
    load().catch((err) => setError(err.message));

    const unsubscribe = subscribeRealtime((message) => {
      if (message.type === "MAP_SESSION_UPDATED") setMapSession(message.data);
      if (message.type === "NAVIGATION_STATUS_UPDATED") {
        setStatus(message.data);
      }
      if (message.type === "SLAM_MAP_UPDATED") {
        setMap(message.data);
      }
    });
    const unsubscribeStatus = subscribeRealtimeStatus(
      (online, isReconnect) => {
        if (online && isReconnect) {
          load().catch((err) => setError(err.message));
        }
      },
    );

    return () => {
      unsubscribe();
      unsubscribeStatus();
    };
  }, []);

  async function handleSend(event) {
    event.preventDefault();
    if (validationMessage) {
      setError(validationMessage);
      return;
    }

    setBusy(true);
    setError(null);
    try {
      setStatus(await sendNavigationGoal({
        ...goal,
        ...(mode === "LOCATION" ? { location_id: selectedLocation.id } : {}),
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    setBusy(true);
    setError(null);
    try {
      setStatus(await cancelNavigation());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const currentGoal = status?.goal;

  return (
    <section className="panel navigation-panel">
      <div className="section-header">
        <div className="section-title-group">
          <span className="section-indicator section-indicator--orange" />
          <h2>NAV2 NAVIGATION</h2>
        </div>
        <span className={status?.nav2_online
          ? "system-online"
          : "muted-label"}>
          Nav2 {status?.nav2_online ? "ONLINE" : "OFFLINE"}
        </span>
      </div>

      {(error || status?.error_message) && (
        <div className="map-error">{error || status.error_message}</div>
      )}

      <div className="navigation-status-grid">
        <span>STATUS <strong>{status?.state ?? "IDLE"}</strong></span>
        <span>X <strong>{formatNumber(currentGoal?.x)}</strong></span>
        <span>Y <strong>{formatNumber(currentGoal?.y)}</strong></span>
        <span>YAW <strong>{formatNumber(currentGoal?.yaw)}</strong></span>
        <span>DISTANCE <strong>{formatNumber(status?.distance_remaining)}</strong></span>
      </div>

      <div className="navigation-mode-switch" aria-label="Navigation goal mode">
        {["LOCATION", "MANUAL"].map((item) => (
          <button
            key={item}
            type="button"
            className={mode === item ? "navigation-mode--active" : ""}
            onClick={() => {
              setMode(item);
              setError(null);
            }}
            disabled={active || busy}
          >
            {item}
          </button>
        ))}
      </div>

      <form className="navigation-form" onSubmit={handleSend}>
        {mode === "LOCATION" && (
          <label className="navigation-location-field">
            LOCATION
            <select
              value={selectedLocationId}
              onChange={(event) => {
                setSelectedLocationId(event.target.value);
                setError(null);
              }}
              disabled={active || busy}
            >
              <option value="">Select active location</option>
              {activeLocations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.code} — {location.name}
                </option>
              ))}
            </select>
          </label>
        )}

        {["x", "y", "yaw"].map((field) => (
          <label key={field}>
            {field.toUpperCase()}
            <input
              type="number"
              step="0.1"
              value={values[field]}
              onChange={(event) => setManualValues((current) => ({
                ...current,
                [field]: event.target.value,
              }))}
              readOnly={mode === "LOCATION"}
              disabled={active || busy}
            />
          </label>
        ))}

        <button className="primary-button" type="submit" disabled={navigateDisabled}>
          NAVIGATE
        </button>
        <button
          className="danger-outline-button"
          type="button"
          onClick={handleCancel}
          disabled={!active || busy}
        >
          CANCEL NAVIGATION
        </button>
      </form>

      {validationMessage && (
        <div className="navigation-validation">{validationMessage}</div>
      )}
    </section>
  );
}


function formatNumber(value) {
  return value != null && Number.isFinite(Number(value))
    ? Number(value).toFixed(2)
    : "-";
}


function parseCoordinate(value) {
  return String(value).trim() === "" ? Number.NaN : Number(value);
}
