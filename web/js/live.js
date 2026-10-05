// Live event stream from the server, re-dispatched as DOM events on a shared EventTarget.
export const liveEvents = new EventTarget();
const RECONNECT_DELAYS_MILLISECONDS = [500, 1000, 2000, 5000, 10000];
let reconnectAttempt = 0;

function setConnectionIndicator(isOnline) {
  document.getElementById("connection-indicator").classList.toggle("online", isOnline);
}

export function connectLiveEvents() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
  socket.addEventListener("open", () => {
    reconnectAttempt = 0;
    setConnectionIndicator(true);
    liveEvents.dispatchEvent(new CustomEvent("connected"));
  });
  socket.addEventListener("message", (messageEvent) => {
    const serverEvent = JSON.parse(messageEvent.data);
    liveEvents.dispatchEvent(new CustomEvent(serverEvent.type, { detail: serverEvent.payload }));
  });
  socket.addEventListener("close", () => {
    setConnectionIndicator(false);
    const reconnectDelay = RECONNECT_DELAYS_MILLISECONDS[Math.min(reconnectAttempt, RECONNECT_DELAYS_MILLISECONDS.length - 1)];
    reconnectAttempt += 1;
    // Backoff only applies while the local server is down or restarting
    window.setTimeout(connectLiveEvents, reconnectDelay);
  });
}
