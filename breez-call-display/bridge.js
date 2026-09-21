(() => {
  if (window.__breezCallDisplayBridge) return;
  window.__breezCallDisplayBridge = true;

  const NativeWebSocket = window.WebSocket;
  const nativeGetUserMedia = navigator.mediaDevices?.getUserMedia?.bind(navigator.mediaDevices);
  let activeSocket = null;
  const microphoneTracks = new Set();

  const publish = (event, payload = {}) => {
    window.postMessage({ source: "breez-call-display", event, payload }, "*");
  };

  window.WebSocket = new Proxy(NativeWebSocket, {
    construct(Target, args) {
      const socket = new Target(...args);
      const url = String(args[0] || "");

      if (url.includes("agent.heybreez.ai") && url.includes("/api/v1/ws/audio/")) {
        activeSocket = socket;
        publish("session_open");

        socket.addEventListener("message", (message) => {
          if (typeof message.data !== "string") return;
          try {
            publish("socket_event", JSON.parse(message.data));
          } catch {
            // Breez also transports binary audio. The visual display only needs JSON events.
          }
        });

        socket.addEventListener("close", () => {
          if (activeSocket === socket) activeSocket = null;
          publish("session_closed");
        });
      }
      return socket;
    }
  });

  Object.defineProperties(window.WebSocket, {
    CONNECTING: { value: NativeWebSocket.CONNECTING },
    OPEN: { value: NativeWebSocket.OPEN },
    CLOSING: { value: NativeWebSocket.CLOSING },
    CLOSED: { value: NativeWebSocket.CLOSED }
  });

  if (nativeGetUserMedia) {
    navigator.mediaDevices.getUserMedia = async (...args) => {
      const stream = await nativeGetUserMedia(...args);
      stream.getAudioTracks().forEach((track) => {
        microphoneTracks.add(track);
        track.addEventListener("ended", () => microphoneTracks.delete(track));
      });
      return stream;
    };
  }

  window.addEventListener("message", (message) => {
    if (message.source !== window || message.data?.source !== "breez-call-display-ui") return;
    const { command, enabled } = message.data;

    if (command === "set_microphone") {
      microphoneTracks.forEach((track) => { track.enabled = Boolean(enabled); });
      publish("microphone_changed", { enabled: Boolean(enabled) });
    }

    if (command === "end_session" && activeSocket?.readyState === NativeWebSocket.OPEN) {
      activeSocket.send(JSON.stringify({ type: "end_session", reason: "user_disconnect" }));
      activeSocket.close(1000, "User ended call");
    }
  });
})();
