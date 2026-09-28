/**
 * AEGIS AI - Live Surveillance Monitor Controller
 * Handles camera commands, single vs 2x2 grid views,
 * fullscreen streaming, snapshot captures, and hardware telemetry.
 */

let currentViewMode = "single";

function switchMonitorView(mode) {
    currentViewMode = mode;
    const singleContainer = document.getElementById("single-view-container");
    const gridContainer = document.getElementById("grid-view-container");
    const badge = document.getElementById("monitor-mode-badge");

    const btnSingle = document.getElementById("view-mode-single");
    const btnGrid = document.getElementById("view-mode-grid");

    if (mode === "grid") {
        if (singleContainer) singleContainer.style.display = "none";
        if (gridContainer) gridContainer.style.display = "grid";
        if (badge) badge.textContent = "2×2 MATRIX";
        if (btnSingle) btnSingle.classList.remove("active");
        if (btnGrid) btnGrid.classList.add("active");
    } else {
        if (singleContainer) singleContainer.style.display = "flex";
        if (gridContainer) gridContainer.style.display = "none";
        if (badge) badge.textContent = "SINGLE FEED";
        if (btnSingle) btnSingle.classList.add("active");
        if (btnGrid) btnGrid.classList.remove("active");
    }
}

function sendCameraCommand(action) {
    const validActions = ['start', 'stop', 'pause', 'resume', 'snapshot'];
    if (!validActions.includes(action)) return;

    fetch(`/api/camera/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            refreshCameraControls();
        } else {
            alert(`Error: ${data.message || 'Operation failed'}`);
        }
    })
    .catch(err => {
        console.error("Camera command error:", err);
    });
}

function takeSnapshot() {
    fetch("/api/camera/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            const snapUrl = `/storage/file/${data.snapshot_path}`;
            window.open(snapUrl, "_blank");
        } else {
            alert("Snapshot failed: " + (data.message || "Unknown error"));
        }
    })
    .catch(err => alert("Error capturing snapshot: " + err));
}

function handleCameraSwitch(selectEl) {
    const camId = selectEl.value;
    if (!camId) return;

    fetch("/api/camera/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_id: parseInt(camId) })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            const streamImg = document.getElementById("main-video-feed");
            if (streamImg) {
                streamImg.src = "/video_feed?t=" + new Date().getTime();
            }
            refreshCameraControls();
        } else {
            alert("Failed to switch camera: " + data.message);
        }
    });
}

function refreshCameraControls() {
    fetch("/api/camera/status")
        .then(res => res.json())
        .then(status => {
            const startBtn = document.getElementById("btn-start");
            const stopBtn = document.getElementById("btn-stop");
            const pauseBtn = document.getElementById("btn-pause");
            const resumeBtn = document.getElementById("btn-resume");

            if (startBtn && stopBtn && pauseBtn && resumeBtn) {
                if (status.running) {
                    startBtn.style.display = "none";
                    stopBtn.style.display = "inline-flex";

                    if (status.paused) {
                        pauseBtn.style.display = "none";
                        resumeBtn.style.display = "inline-flex";
                    } else {
                        pauseBtn.style.display = "inline-flex";
                        resumeBtn.style.display = "none";
                    }
                } else {
                    startBtn.style.display = "inline-flex";
                    stopBtn.style.display = "none";
                    pauseBtn.style.display = "none";
                    resumeBtn.style.display = "none";
                }
            }

            // Update FPS & Diagnostic Readouts
            const infoText = document.getElementById("stream-fps-counter");
            if (infoText) {
                infoText.textContent = `${status.fps} FPS | ${status.active_tracks_count || 0} Active Track(s)`;
            }

            const diagFps = document.getElementById("diag-fps");
            if (diagFps) {
                diagFps.textContent = `${status.fps} FPS`;
            }

            const diagTracks = document.getElementById("diag-tracks");
            if (diagTracks) {
                diagTracks.textContent = `${status.active_tracks_count || 0}`;
            }
        })
        .catch(() => {});
}

function toggleFullscreen(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;

    if (!document.fullscreenElement) {
        if (el.requestFullscreen) {
            el.requestFullscreen();
        } else if (el.webkitRequestFullscreen) {
            el.webkitRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    refreshCameraControls();
    setInterval(refreshCameraControls, 3000);
});
