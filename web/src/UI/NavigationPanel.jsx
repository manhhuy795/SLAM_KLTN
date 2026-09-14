import { useEffect, useState } from "react";

import {
  cancelNavigation,
  getNavigationPath,
  getNavigationStatus,
  sendNavigationGoal,
} from "../services/api";
import {
  subscribeRealtime,
  subscribeRealtimeStatus,
} from "../services/realtime";


const ACTIVE_STATES = new Set(["SENDING", "NAVIGATING"]);


export default function NavigationPanel() {
  const [status, setStatus] = useState(null);
  const [values, setValues] = useState({
    x: "1.0",
    y: "0.0",
    yaw: "0.0",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function load() {
    const nextStatus = await getNavigationStatus();
    await getNavigationPath();
    setStatus(nextStatus);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));

    const unsubscribe = subscribeRealtime((message) => {
      if (message.type === "NAVIGATION_STATUS_UPDATED") {
        setStatus(message.data);
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
    const goal = {
      x: Number(values.x),
      y: Number(values.y),
      yaw: Number(values.yaw),
    };
    if (!Object.values(goal).every(Number.isFinite)) {
      setError("Coordinates must be finite.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      setStatus(await sendNavigationGoal(goal));
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

  const goal = status?.goal;
  const active = ACTIVE_STATES.has(status?.state);

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

      {error && <div className="map-error">{error}</div>}

      <div className="navigation-status-grid">
        <span>STATUS <strong>{status?.state ?? "IDLE"}</strong></span>
        <span>X <strong>{formatNumber(goal?.x)}</strong></span>
        <span>Y <strong>{formatNumber(goal?.y)}</strong></span>
        <span>YAW <strong>{formatNumber(goal?.yaw)}</strong></span>
        <span>DISTANCE <strong>{formatNumber(status?.distance_remaining)}</strong></span>
      </div>

      <form className="navigation-form" onSubmit={handleSend}>
        {["x", "y", "yaw"].map((field) => (
          <label key={field}>
            {field.toUpperCase()}
            <input
              type="number"
              step="0.1"
              value={values[field]}
              onChange={(event) => setValues((current) => ({
                ...current,
                [field]: event.target.value,
              }))}
              disabled={active || busy}
            />
          </label>
        ))}
        <button className="primary-button" type="submit" disabled={active || busy}>
          SEND GOAL
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
    </section>
  );
}


function formatNumber(value) {
  return Number.isFinite(Number(value))
    ? Number(value).toFixed(2)
    : "-";
}
