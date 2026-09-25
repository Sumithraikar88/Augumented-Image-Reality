/**
 * Live AR camera — browser <-> Django AR loop.
 *
 * Grab frames from getUserMedia, JPEG-encode them, POST to /api/frame/,
 * render the augmented JPEG the server returns. Loop via setTimeout so we
 * only keep one request in flight (self-clocking = adapts to server speed).
 */
(function () {
  "use strict";

  const video = document.getElementById("video");
  const outImg = document.getElementById("live-out");
  const statusEl = document.getElementById("live-status");
  const statsEl = document.getElementById("live-stats");
  const startBtn = document.getElementById("start-btn");
  const stopBtn = document.getElementById("stop-btn");
  const snapBtn = document.getElementById("snapshot-btn");

  const modeSel = document.getElementById("mode");
  const overlaySel = document.getElementById("overlay");
  const targetSel = document.getElementById("target");
  const filterSel = document.getElementById("filter");
  const alphaInput = document.getElementById("alpha");
  const signalEl = document.getElementById("signal-state");
  const latencyEl = document.getElementById("latency-readout");
  const confidenceEl = document.getElementById("confidence-readout");

  let running = false;
  let busy = false;
  let stream = null;
  let canvas = null;
  let lastServerMs = 0;
  let lastRoundtripMs = 0;

  const API_URL = "/api/frame/";

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function setSignal(text, active = false) {
    if (!signalEl) return;
    signalEl.textContent = text;
    signalEl.classList.toggle("active", active);
  }

  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 960 }, height: { ideal: 720 } },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      running = true;
      startBtn.disabled = true;
      stopBtn.disabled = false;
      snapBtn.disabled = false;
      setSignal("CONNECTING", true);
      setStatus("camera on — streaming to Django…");
      loop();
    } catch (err) {
      setSignal("ERROR");
      setStatus("camera error: " + err.message);
    }
  }

  function stopCamera() {
    running = false;
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
    startBtn.disabled = false;
    stopBtn.disabled = true;
    snapBtn.disabled = true;
    outImg.classList.add("hidden");
    video.style.visibility = "visible";
    setSignal("STANDBY");
    if (latencyEl) latencyEl.textContent = "-- ms";
    if (confidenceEl) confidenceEl.textContent = "--%";
    setStatus("stopped");
  }

  function grabFrame() {
    if (!canvas) canvas = document.createElement("canvas");
    const w = 960;
    const scale = Math.min(1, w / video.videoWidth || 1);
    canvas.width = Math.round(video.videoWidth * scale) || 640;
    canvas.height = Math.round(video.videoHeight * scale) || 480;
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.7);
  }

  async function sendFrame() {
    busy = true;
    const t0 = performance.now();
    try {
      const resp = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: grabFrame(),
          mode: modeSel.value,
          overlay_id: overlaySel.value || null,
          target_id: targetSel.value || null,
          filter: filterSel.value,
          alpha: alphaInput.value,
        }),
      });
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "server error");

      lastServerMs = data.stats.processing_ms;
      lastRoundtripMs = Math.round(performance.now() - t0);
      outImg.src = data.stats.image;
      outImg.classList.remove("hidden");
      video.style.visibility = "hidden";

      const s = data.stats;
      const metrics = s.image_metrics || {};
      setSignal(s.tracking_confidence ? "TRACKING" : "SEARCHING", true);
      if (latencyEl) latencyEl.textContent = `${lastRoundtripMs} ms`;
      if (confidenceEl) confidenceEl.textContent = `${s.tracking_confidence || 0}%`;
      statsEl.classList.remove("hidden");
      statsEl.textContent =
        `mode ${s.mode} | markers ${s.aruco_count} [${s.marker_ids.join(",")}] | ` +
        `matches ${s.good_matches} | inliers ${s.inliers} | confidence ${s.tracking_confidence || 0}% | ` +
        `light ${metrics.exposure || "--"} | sharpness ${metrics.sharpness || "--"}`;
      setStatus("live");
    } catch (err) {
      setStatus("error: " + err.message + " — retrying…");
    } finally {
      busy = false;
    }
  }

  function loop() {
    if (!running) return;
    if (!busy && video.readyState >= 2) {
      sendFrame();
    }
    // Self-clocking: wait a bit longer when the server is slow.
    const wait = Math.max(30, Math.min(120, lastServerMs / 3));
    setTimeout(loop, wait);
  }

  async function snapshot() {
    try {
      const blob = await (await fetch(outImg.src)).blob();
      const fd = new FormData();
      fd.append("title", "Live snapshot " + new Date().toLocaleString());
      fd.append("image", blob, "snapshot.jpg");
      const resp = await fetch("/api/snapshot/", {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        body: fd,
      });
      const data = await resp.json();
      if (data.ok) setStatus("snapshot saved to gallery ✔");
      else setStatus("snapshot failed: " + (data.error || "?"));
    } catch (err) {
      setStatus("snapshot failed: " + err.message);
    }
  }

  startBtn.addEventListener("click", startCamera);
  stopBtn.addEventListener("click", stopCamera);
  snapBtn.addEventListener("click", snapshot);
  alphaInput.addEventListener("input", () => {
    document.getElementById("alpha-val").textContent = alphaInput.value;
  });
})();
