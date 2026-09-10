const WS_URL =
  import.meta.env.VITE_WS_URL ||
  'ws://127.0.0.1:8000/ws';

let socket = null;
let reconnectTimer = null;
let shouldReconnect = false;
let everConnected = false;

const messageListeners = new Set();
const statusListeners = new Set();


function notifyStatus(online) {
  statusListeners.forEach((listener) => {
    listener(online);
  });
}


function connectSocket() {
  if (
    !shouldReconnect ||
    socket?.readyState === WebSocket.OPEN ||
    socket?.readyState === WebSocket.CONNECTING
  ) {
    return;
  }

  try {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      const isReconnect = everConnected;
      everConnected = true;
      statusListeners.forEach((listener) => {
        listener(true, isReconnect);
      });
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        if (message?.type) {
          messageListeners.forEach((listener) => {
            listener(message);
          });
        }
      } catch (error) {
        console.error('Invalid realtime message:', error);
      }
    };

    socket.onerror = () => {
      socket?.close();
    };

    socket.onclose = () => {
      socket = null;
      notifyStatus(false);

      if (shouldReconnect && reconnectTimer === null) {
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connectSocket();
        }, 1000);
      }
    };
  } catch (error) {
    console.error('Realtime connection failed:', error);
    socket = null;

    if (shouldReconnect && reconnectTimer === null) {
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connectSocket();
      }, 1000);
    }
  }
}


export function connectRealtime() {
  shouldReconnect = true;
  connectSocket();

  return disconnectRealtime;
}


export function disconnectRealtime() {
  shouldReconnect = false;
  everConnected = false;

  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  if (socket !== null) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }

  notifyStatus(false);
}


export function subscribeRealtime(listener) {
  messageListeners.add(listener);

  return () => {
    messageListeners.delete(listener);
  };
}


export function subscribeRealtimeStatus(listener) {
  statusListeners.add(listener);

  return () => {
    statusListeners.delete(listener);
  };
}
