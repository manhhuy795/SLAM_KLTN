const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  "http://127.0.0.1:8000/api"
).replace(/\/$/, "");


async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let message = "API request failed";

    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {
      // Không có JSON error body
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}


// ======================
// ROBOTS
// ======================

export function getRobots() {
  return request("/robots");
}

export function getRobot(robotId) {
  return request(`/robots/${robotId}`);
}

export function updateRobotStatus(robotId, data) {
  return request(`/robots/${robotId}/status`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function requestSafeStop() {
  return request("/robots/safe-stop", {
    method: "POST",
  });
}


// ======================
// LOCATIONS
// ======================

export function getLocations() {
  return request("/locations");
}

export function createLocation(data) {
  return request("/locations", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateLocation(locationId, data) {
  return request(`/locations/${locationId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteLocation(locationId) {
  return request(`/locations/${locationId}`, {
    method: "DELETE",
  });
}


// ======================
// PRODUCTS
// ======================

export function getProducts() {
  return request("/products");
}

export function createProduct(data) {
  return request("/products", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateProduct(productId, data) {
  return request(`/products/${productId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteProduct(productId) {
  return request(`/products/${productId}`, {
    method: "DELETE",
  });
}


// ======================
// TASKS
// ======================

export function getTasks() {
  return request("/tasks");
}

export function getTask(taskId) {
  return request(`/tasks/${taskId}`);
}

export function createTask(data) {
  return request("/tasks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function pauseTask(taskId) {
  return request(`/tasks/${taskId}/pause`, {
    method: "PATCH",
  });
}

export function resumeTask(taskId) {
  return request(`/tasks/${taskId}/resume`, {
    method: "PATCH",
  });
}

export function cancelTask(taskId) {
  return request(`/tasks/${taskId}/cancel`, {
    method: "PATCH",
  });
}


// ======================
// ALERTS
// ======================

export function getAlerts() {
  return request("/alerts");
}

export function getOperators() {
  return request("/operators");
}

export function acknowledgeAlert(
  alertId,
  operatorId
) {
  return request(
    `/alerts/${alertId}/acknowledge`,
    {
      method: "PATCH",
      body: JSON.stringify({
        operator_id: operatorId,
      }),
    }
  );
}

export function resolveAlert(
  alertId,
  operatorId
) {
  return request(
    `/alerts/${alertId}/resolve`,
    {
      method: "PATCH",
      body: JSON.stringify({
        operator_id: operatorId,
      }),
    }
  );
}


// ======================
// HISTORY
// ======================

export function getHistory(filters = {}) {
  const params = new URLSearchParams();

  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, value);
    }
  });

  const query = params.toString();
  return request(`/history${query ? `?${query}` : ""}`);
}

export function createTaskProof(taskId, data) {
  return request(`/tasks/${taskId}/proofs`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getTaskProofs(taskId) {
  return request(`/tasks/${taskId}/proofs`);
}


// ======================
// ROS BRIDGE
// ======================

export function getRosState() {
  return request("/ros/state");
}

export function getRosMap() {
  return request("/ros/map");
}

export function getRosPose() {
  return request("/ros/pose");
}
