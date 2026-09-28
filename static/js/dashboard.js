/**
 * AEGIS AI - Dashboard Controller & SOC Telemetry Engine
 * Manages animated counter metrics, live multi-chart visualizations,
 * camera controls, live event ticker, and snapshot lightbox.
 */

let hourlyChart = null;
let recognitionChart = null;
let entityChart = null;
let currentZoom = 1.0;
let activeRange = "today";

// Smooth Counter Animation using requestAnimationFrame
function animateCounter(id, targetValue, duration = 800) {
    const el = document.getElementById(id);
    if (!el) return;

    // Handle strings like "142 MB"
    let suffix = "";
    let cleanVal = targetValue;
    if (typeof targetValue === "string" && targetValue.includes("MB")) {
        suffix = " MB";
        cleanVal = parseFloat(targetValue) || 0;
    } else {
        cleanVal = parseInt(targetValue, 10) || 0;
    }

    const currentText = el.textContent.replace(" MB", "").trim();
    const startVal = parseFloat(currentText) || 0;
    if (startVal === cleanVal) return;

    const startTime = performance.now();

    function step(timestamp) {
        const progress = Math.min((timestamp - startTime) / duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 3); // Cubic ease out
        const currentVal = Math.round(startVal + (cleanVal - startVal) * easeProgress);

        el.textContent = currentVal + suffix;
        if (progress < 1) {
            requestAnimationFrame(step);
        } else {
            el.textContent = cleanVal + suffix;
        }
    }
    requestAnimationFrame(step);
}

// Chart Initializers
function initHourlyChart(labels, data, rangeLabel = "24-Hour Curve") {
    const ctx = document.getElementById("hourlyEventsChart");
    if (!ctx) return;

    if (hourlyChart) {
        hourlyChart.destroy();
    }

    const lbl = document.getElementById("chart-timeline-label");
    if (lbl) lbl.textContent = rangeLabel;

    hourlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: "Captures",
                data: data,
                borderColor: '#388bfd',
                backgroundColor: 'rgba(56, 139, 253, 0.12)',
                borderWidth: 2,
                fill: true,
                tension: 0.35,
                pointBackgroundColor: '#58a6ff',
                pointBorderColor: '#0d1117',
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#161b22',
                    titleColor: '#f0f6fc',
                    bodyColor: '#8b949e',
                    borderColor: '#30363d',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(56, 75, 112, 0.2)' },
                    ticks: { color: '#8b949e', maxTicksLimit: 12, font: { family: 'JetBrains Mono', size: 10 } }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(56, 75, 112, 0.2)' },
                    ticks: { color: '#8b949e', stepSize: 1, font: { family: 'JetBrains Mono', size: 10 } }
                }
            }
        }
    });
}

function initRecognitionChart(known, unknown) {
    const ctx = document.getElementById("recognitionPieChart");
    if (!ctx) return;

    if (recognitionChart) {
        recognitionChart.destroy();
    }

    const total = known + unknown;
    const hasData = total > 0;

    recognitionChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Known', 'Unknown'],
            datasets: [{
                data: hasData ? [known, unknown] : [0, 1],
                backgroundColor: hasData ? ['#10b981', '#ef4444'] : ['#21262d', '#21262d'],
                borderColor: '#0a0e17',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#8b949e', font: { size: 11 }, boxWidth: 12 }
                }
            }
        }
    });
}

function initEntityChart(people, vehicles, animals) {
    const ctx = document.getElementById("entityBarChart");
    if (!ctx) return;

    if (entityChart) {
        entityChart.destroy();
    }

    entityChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['People', 'Vehicles', 'Animals'],
            datasets: [{
                data: [people, vehicles, animals],
                backgroundColor: ['#06b6d4', '#3b82f6', '#f59e0b'],
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#8b949e', font: { size: 10 } }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(56, 75, 112, 0.2)' },
                    ticks: { color: '#8b949e', stepSize: 1, font: { family: 'JetBrains Mono', size: 10 } }
                }
            }
        }
    });
}

// Range switcher (Today, 7d, 30d)
function switchAnalyticsRange(range, btnEl) {
    activeRange = range;
    document.querySelectorAll(".time-filter-btn").forEach(b => b.classList.remove("active"));
    if (btnEl) btnEl.classList.add("active");

    fetch(`/api/statistics?range=${range}`)
        .then(res => res.json())
        .then(res => {
            if (res.status === "success") {
                updateDashboardFromAPI(res);
            }
        })
        .catch(err => console.error("Error switching range:", err));
}

// Poll & Refresh Telemetry
function refreshDashboardMetrics() {
    fetch(`/api/statistics?range=${activeRange}`)
        .then(res => res.json())
        .then(res => {
            if (res.status === "success") {
                updateDashboardFromAPI(res);
            }
        })
        .catch(err => console.error("Error polling metrics:", err));
}

function updateDashboardFromAPI(res) {
    const m = res.metrics;
    animateCounter("stat-today-events", m.today_events);
    animateCounter("stat-people-detected", m.people_detected);
    animateCounter("stat-known-people", m.known_people);
    animateCounter("stat-unknown-people", m.unknown_people);
    animateCounter("stat-vehicles", m.vehicles);
    animateCounter("stat-animals", m.animals);
    animateCounter("stat-suspicious", m.suspicious_count || 0);
    animateCounter("stat-storage-used", `${m.storage_used_mb} MB`);

    // Update Hourly/Range Chart
    if (res.hourly_chart) {
        initHourlyChart(res.hourly_chart.labels, res.hourly_chart.data, res.hourly_chart.title || "Timeline");
    }

    // Update Doughnut & Bar Charts
    initRecognitionChart(m.known_people, m.unknown_people);
    initEntityChart(m.people_detected, m.vehicles, m.animals);

    // Update Camera status pill & active tracks
    updateCameraStatus(res.camera_status);
}

function updateCameraStatus(status) {
    if (!status) return;
    const pill = document.getElementById("camera-status-indicator");
    if (pill) {
        if (status.online) {
            pill.className = "camera-status-pill";
            pill.innerHTML = `<span class="pulse-dot"></span> 🟢 Camera Online (${status.fps} FPS)`;
        } else {
            pill.className = "camera-status-pill offline";
            pill.innerHTML = `<span class="pulse-dot"></span> 🔴 Camera Offline`;
        }
    }

    const tracksBadge = document.getElementById("stream-active-tracks-badge");
    if (tracksBadge) {
        tracksBadge.textContent = `${status.active_tracks_count || 0} Track(s)`;
    }

    const fpsCounter = document.getElementById("stream-fps-counter");
    if (fpsCounter) {
        fpsCounter.textContent = `${status.fps} FPS | ${status.active_tracks_count || 0} Active Track(s)`;
    }

    // Update play/pause buttons
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
}

// Camera Commands
function sendCameraCommand(action) {
    fetch(`/api/camera/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            refreshDashboardMetrics();
        } else {
            alert(`Error: ${data.message || 'Operation failed'}`);
        }
    })
    .catch(err => console.error("Camera command error:", err));
}

function triggerSnapshotCapture() {
    fetch(`/api/camera/snapshot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            const snapUrl = `/storage/file/${data.snapshot_path}`;
            openSnapshotLightbox(snapUrl, "Manual Operator Snapshot", new Date().toLocaleTimeString());
        } else {
            alert("Snapshot error: " + (data.message || "Failed"));
        }
    })
    .catch(err => alert("Error capturing snapshot: " + err));
}

// Fullscreen API Helper
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

// Snapshot Lightbox Controls
function openSnapshotLightbox(src, title = "Forensic Snapshot", meta = "") {
    const modal = document.getElementById("snapshot-lightbox-modal");
    const img = document.getElementById("lightbox-img");
    const titleEl = document.getElementById("lightbox-title");
    const metaEl = document.getElementById("lightbox-meta");
    const dlLink = document.getElementById("lightbox-download-link");

    if (!modal || !img) return;

    img.src = src;
    currentZoom = 1.0;
    img.style.transform = `scale(1.0)`;

    if (titleEl) titleEl.innerHTML = `<span>📸</span> ${title}`;
    if (metaEl) metaEl.textContent = meta;
    if (dlLink) {
        dlLink.href = src;
        dlLink.setAttribute("download", src.split("/").pop());
    }

    modal.classList.add("show");
}

function closeSnapshotLightbox() {
    const modal = document.getElementById("snapshot-lightbox-modal");
    if (modal) modal.classList.remove("show");
}

function zoomSnapshot(factor) {
    const img = document.getElementById("lightbox-img");
    if (!img) return;
    currentZoom = Math.max(0.5, Math.min(3.0, currentZoom * factor));
    img.style.transform = `scale(${currentZoom})`;
}

function resetSnapshotZoom() {
    const img = document.getElementById("lightbox-img");
    if (!img) return;
    currentZoom = 1.0;
    img.style.transform = `scale(1.0)`;
}

// Prepend live events to ticker
function prependLiveEventTicker(notif) {
    const ticker = document.getElementById("live-event-ticker");
    if (!ticker) return;

    const item = document.createElement("div");
    const isCrit = notif.severity === "critical" || (notif.title && notif.title.includes("UNAUTHORIZED"));
    item.className = `ticker-item ${isCrit ? 'critical' : 'warning'}`;

    let snapHtml = `<div class="ticker-thumb" style="background:#1e293b; display:flex; align-items:center; justify-content:center;">📷</div>`;
    if (notif.snapshot_url) {
        snapHtml = `<img src="${notif.snapshot_url}" alt="Snap" class="ticker-thumb" onclick="openSnapshotLightbox('${notif.snapshot_url}', '${notif.title}', '${notif.time || 'Immediate'}')">`;
    }

    item.innerHTML = `
        ${snapHtml}
        <div class="ticker-details">
            <div class="ticker-title">${escapeHTML(notif.title)}</div>
            <div class="ticker-meta">
                <span>${notif.time || 'Just now'}</span>
                <span>•</span>
                <span style="color: #f87171;">${notif.category || 'ALERT'}</span>
            </div>
        </div>
        ${notif.event_id ? `<a href="/events/${notif.event_id}" class="btn-ctrl" style="padding: 3px 8px; font-size: 11px;">View</a>` : ''}
    `;

    ticker.insertBefore(item, ticker.firstChild);

    // Keep ticker capped at 8 items
    if (ticker.children.length > 8) {
        ticker.removeChild(ticker.lastChild);
    }
}

// Initialization on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
    refreshDashboardMetrics();
    setInterval(refreshDashboardMetrics, 5000);
});
