const host = typeof window === "undefined" ? "127.0.0.1" : window.location.hostname;
const API = (import.meta.env.VITE_API_BASE_URL || `http://${host}:8000/api`).replace(/\/$/, "");
export const agvUrl = (path) => `${API}/agv/LINE-01${path}`;
async function request(path, options = {}) {
  const response = await fetch(agvUrl(path), {
    ...options,
    headers: {"Content-Type": "application/json", ...options.headers},
  });
  if (!response.ok) {
    const json = await response.json().catch(() => ({}));
    throw new Error(json.detail || `AGV request failed (${response.status})`);
  }
  return response.json();
}
export const getAgvState = () => request("/state");
export const sendAgvCommand = (action, mission_id) =>
  request("/command", {method: "POST", body: JSON.stringify({action, ...(mission_id ? {mission_id} : {})})});
export const getAgvLogs = () => request("/logs");
export const exportAgvLogs = () => window.open(agvUrl("/export_csv"), "_blank", "noopener,noreferrer");
