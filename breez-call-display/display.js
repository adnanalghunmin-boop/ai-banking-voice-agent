(() => {
  if (window.__breezCallDisplayUI) return;
  window.__breezCallDisplayUI = true;

  let overlay;
  let timerId;
  let startedAt = 0;
  let micEnabled = true;
  let currentRole = "assistant";

  const esc = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const formatTime = (seconds) => {
    const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
    const remainder = (seconds % 60).toString().padStart(2, "0");
    return `${minutes}:${remainder}`;
  };

  function createOverlay() {
    if (overlay) return;
    overlay = document.createElement("section");
    overlay.id = "breez-call-display";
    overlay.innerHTML = `
      <div class="bcd-shell">
        <header class="bcd-header">
          <div class="bcd-brand" aria-label="MENADEVS voice assistant">
            <img src="${chrome.runtime.getURL("assets/menadevs-logo.png")}" alt="MENADEVS">
          </div>
          <div class="bcd-product">MENADEVS • AI VOICE BANKING AGENT</div>
          <div class="bcd-live"><span></span> LIVE CALL <b>•</b> <time>00:00</time></div>
        </header>

        <main class="bcd-main">
          <div class="bcd-progress" aria-label="Call state">
            <div class="bcd-step" data-step="connected"><span>✓</span><small>Connected</small></div>
            <i></i>
            <div class="bcd-step" data-step="listening"><span>◉</span><small>Listening</small></div>
            <i></i>
            <div class="bcd-step" data-step="thinking"><span>◇</span><small>Processing</small></div>
            <i></i>
            <div class="bcd-step" data-step="speaking"><span>≡</span><small>Responding</small></div>
          </div>

          <div class="bcd-role">ASSISTANT</div>
          <div class="bcd-transcript" dir="auto"><span>بدء المكالمة…</span></div>

          <div class="bcd-wave" aria-hidden="true">
            ${Array.from({ length: 42 }, (_, index) => `<i style="--i:${index}"></i>`).join("")}
          </div>

        </main>

        <footer class="bcd-controls">
          <button class="bcd-round bcd-mic" type="button" title="Mute microphone" aria-label="Mute microphone">⌁</button>
          <button class="bcd-end" type="button"><span>×</span> End call</button>
          <button class="bcd-round bcd-minimize" type="button" title="Hide display" aria-label="Hide display">—</button>
        </footer>
      </div>`;

    document.documentElement.appendChild(overlay);
    overlay.querySelector(".bcd-end").addEventListener("click", endCall);
    overlay.querySelector(".bcd-minimize").addEventListener("click", () => overlay.classList.add("bcd-hidden"));
    overlay.querySelector(".bcd-mic").addEventListener("click", toggleMicrophone);
  }

  function startSession() {
    createOverlay();
    currentRole = "assistant";
    startedAt = Date.now();
    micEnabled = true;
    overlay.classList.remove("bcd-hidden", "bcd-muted");
    overlay.classList.add("bcd-fullscreen");
    overlay.querySelector(".bcd-transcript span").textContent = "بدء المكالمة…";
    fitTranscript();
    setState("connected");
    clearInterval(timerId);
    timerId = setInterval(() => {
      overlay.querySelector("time").textContent = formatTime(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
  }

  function setState(state) {
    if (!overlay) return;
    overlay.dataset.state = state;
    overlay.querySelectorAll(".bcd-step").forEach((step) => {
      step.classList.toggle("active", step.dataset.step === state || (state === "connected" && step.dataset.step === "connected"));
    });
  }

  function updateTranscript(params) {
    if (!overlay || !params?.text) return;
    currentRole = params.role === "user" ? "user" : "assistant";
    overlay.querySelector(".bcd-role").textContent = currentRole === "user" ? "YOU" : "ASSISTANT";
    overlay.querySelector(".bcd-role").dataset.role = currentRole;
    renderLiveTranscript(params.text.trim());
    fitTranscript();
  }

  function renderLiveTranscript(text) {
    const transcript = overlay?.querySelector(".bcd-transcript span");
    if (!transcript) return;

    const match = text.match(/^(.*?)(\S+)$/su);
    if (!match) {
      transcript.textContent = text;
      return;
    }

    transcript.innerHTML = `${esc(match[1])}<mark class="bcd-new-word">${esc(match[2])}</mark>`;
  }

  function fitTranscript() {
    const box = overlay?.querySelector(".bcd-transcript");
    const text = box?.querySelector("span");
    if (!box || !text) return;

    box.style.fontSize = "";
    requestAnimationFrame(() => {
      let size = Number.parseFloat(getComputedStyle(box).fontSize);
      const minimumSize = window.innerWidth <= 700 ? 24 : 28;

      while (text.scrollHeight > box.clientHeight && size > minimumSize) {
        size -= 1;
        box.style.fontSize = `${size}px`;
      }
    });
  }

  function toggleMicrophone() {
    micEnabled = !micEnabled;
    overlay.classList.toggle("bcd-muted", !micEnabled);
    overlay.querySelector(".bcd-mic").textContent = micEnabled ? "⌁" : "×";
    window.postMessage({ source: "breez-call-display-ui", command: "set_microphone", enabled: micEnabled }, "*");
  }

  function endCall() {
    window.postMessage({ source: "breez-call-display-ui", command: "end_session" }, "*");
    const nativeEndButton = [...document.querySelectorAll("button")]
      .find((button) => /end test/i.test(button.textContent || ""));
    nativeEndButton?.click();
    finishSession();
  }

  function finishSession() {
    clearInterval(timerId);
    if (!overlay) return;
    overlay.dataset.state = "ended";
    setTimeout(() => overlay?.classList.add("bcd-hidden"), 900);
  }

  window.addEventListener("message", (message) => {
    if (message.source !== window || message.data?.source !== "breez-call-display") return;
    const { event, payload } = message.data;
    if (event === "session_open") startSession();
    if (event === "session_closed") finishSession();
    if (event !== "socket_event") return;

    if (payload.method === "transcript_update") updateTranscript(payload.params);
    if (payload.method === "agent_state") setState(payload.params?.state);
    if (payload.method === "agent_speaking") setState(payload.params?.is_speaking ? "speaking" : "listening");
  });

  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.shiftKey && event.code === "KeyB") {
      createOverlay();
      overlay.classList.toggle("bcd-hidden");
    }
  });
})();
