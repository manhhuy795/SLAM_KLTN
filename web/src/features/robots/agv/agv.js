const host = typeof window === "undefined" ? "127.0.0.1" : window.location.hostname;
const API = (import.meta.env.VITE_API_BASE_URL || `http://${host}:8000/api`).replace(/\/$/, "");
export const agvUrl = (path, robotCode = "LINE-01") => `${API}/agv/${encodeURIComponent(robotCode)}${path}`;
async function request(path, robotCode, options = {}) {
  const response = await fetch(agvUrl(path, robotCode), {
    ...options,
    headers: {"Content-Type": "application/json", ...options.headers},
  });
  if (!response.ok) {
    const json = await response.json().catch(() => ({}));
    throw new Error(json.detail || `AGV request failed (${response.status})`);
  }
  return response.json();
}
export const getAgvState = (robotCode = "LINE-01") => request("/state", robotCode);
export const getAgvMissionConfig = (robotCode) => request("/mission-config", robotCode);
export const saveAgvMissionConfig = (robotCode, data, token) => request("/mission-config", robotCode, {
  method: "PUT", headers: { "X-WRMS-Policy-Token": token }, body: JSON.stringify(data),
});
export const previewAgvMission = (robotCode, cargoClass, returnStation) =>
  request(`/mission-preview?${new URLSearchParams({ cargo_class: cargoClass, return_station: returnStation })}`, robotCode);
export const sendAgvCommand = (action, mission_id, robotCode = "LINE-01") =>
  request("/command", robotCode, {method: "POST", body: JSON.stringify({action, ...(mission_id ? {mission_id} : {})})});
export const getAgvLogs = (robotCode = "LINE-01") => request("/logs", robotCode);
export const exportAgvLogs = (robotCode = "LINE-01") => window.open(agvUrl("/export_csv", robotCode), "_blank", "noopener,noreferrer");
