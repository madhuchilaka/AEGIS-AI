/**
 * AEGIS AI - Real-Time Notification & Alerting Engine
 * Connects to Server-Sent Events (SSE), handles audio chimes,
 * displays interactive toasts, manages the Critical Threat Modal,
 * and updates SOC top bar badges in real-time.
 */

class NotificationEngine {
    constructor() {
        this.toastContainer = null;
        this.audioCtx = null;
        this.currentThreatEventId = null;
        this.currentThreatNotifId = null;
        this.initDOM();
        this.initAudio();
        this.initSSE();
        this.initBrowserNotifications();
    }

    initDOM() {
        let container = document.getElementById("toast-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "toast-container";
            container.className = "toast-container";
            document.body.appendChild(container);
        }
        this.toastContainer = container;
    }

    initAudio() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.audioCtx = new AudioContext();
            }
        } catch (e) {
            console.warn("AudioContext not supported:", e);
        }
    }

    playAlertChime(severity = "warning") {
        if (typeof audioAlertsEnabled !== "undefined" && !audioAlertsEnabled) {
            return;
        }
        if (!this.audioCtx) return;
        try {
            if (this.audioCtx.state === "suspended") {
                this.audioCtx.resume();
            }
            const now = this.audioCtx.currentTime;
            const osc = this.audioCtx.createOscillator();
            const gain = this.audioCtx.createGain();

            osc.connect(gain);
            gain.connect(this.audioCtx.destination);

            if (severity === "critical" || severity === "UNAUTHORIZED" || severity === "SUSPICIOUS") {
                // High urgent cyber warble
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(880, now); // A5
                osc.frequency.setValueAtTime(440, now + 0.12);
                osc.frequency.setValueAtTime(880, now + 0.24);
                gain.gain.setValueAtTime(0.2, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.45);
                osc.start(now);
                osc.stop(now + 0.45);
            } else {
                // Gentle ping
                osc.type = "sine";
                osc.frequency.setValueAtTime(659.25, now); // E5
                osc.frequency.exponentialRampToValueAtTime(880, now + 0.15); // A5
                gain.gain.setValueAtTime(0.12, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                osc.start(now);
                osc.stop(now + 0.35);
            }
        } catch (e) {
            // Audio context may be restricted before user gesture
        }
    }

    initBrowserNotifications() {
        if ("Notification" in window && Notification.permission === "default") {
            document.addEventListener("click", () => {
                if (Notification.permission === "default") {
                    Notification.requestPermission();
                }
            }, { once: true });
        }
    }

    initSSE() {
        if (!window.EventSource) {
            console.warn("SSE not supported, running polling fallback.");
            this.startPollingFallback();
            return;
        }

        const source = new EventSource("/api/notifications/stream");

        source.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleNewNotification(data);
            } catch (e) {
                console.error("Error parsing SSE event:", e);
            }
        };

        source.onerror = () => {
            // Reconnection handled automatically by browser EventSource
        };
    }

    startPollingFallback() {
        let lastNotifId = 0;
        setInterval(() => {
            fetch("/api/notifications?limit=5")
                .then(res => res.json())
                .then(data => {
                    if (data.status === "success" && data.notifications.length > 0) {
                        const latest = data.notifications[0];
                        if (latest.id > lastNotifId && lastNotifId !== 0) {
                            this.handleNewNotification(latest);
                        }
                        lastNotifId = latest.id;
                    }
                })
                .catch(() => {});
        }, 5000);
    }

    handleNewNotification(notif) {
        // 1. Play Audio Alert
        this.playAlertChime(notif.severity);

        // 2. Render On-Screen Toast
        this.renderToast(notif);

        // 3. Update Nav and Top Badges
        this.updateUnreadCount(1);

        // 4. Trigger Threat Modal if Critical or Unauthorized
        const isCritical = notif.severity === "critical" || 
                           notif.category === "UNAUTHORIZED" || 
                           notif.category === "CRITICAL" ||
                           (notif.title && notif.title.includes("UNAUTHORIZED"));

        if (isCritical) {
            this.showThreatModal(notif);
        }

        // 5. Fire Web Notification if allowed
        if ("Notification" in window && Notification.permission === "granted") {
            try {
                new Notification(notif.title, {
                    body: notif.message,
                    icon: notif.snapshot_url || "/static/images/logo.png"
                });
            } catch (e) {}
        }

        // 6. If on dashboard, prepend to live event ticker if present
        if (typeof prependLiveEventTicker === "function") {
            prependLiveEventTicker(notif);
        }
    }

    renderToast(notif) {
        const toast = document.createElement("div");
        const severityClass = notif.severity === "critical" ? "toast-critical" :
                              (notif.severity === "warning" ? "toast-warning" : "toast-info");
        toast.className = `toast ${severityClass}`;

        let icon = "⚠️";
        if (notif.severity === "critical") icon = "🚨";
        else if (notif.severity === "info") icon = "ℹ️";

        toast.innerHTML = `
            <div class="toast-icon">${icon}</div>
            <div class="toast-content" style="flex: 1;">
                <h5>${escapeHTML(notif.title)}</h5>
                <p>${escapeHTML(notif.message)}</p>
                <div class="toast-time">${notif.time || 'Just now'}</div>
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;

        if (notif.snapshot_url) {
            const img = document.createElement("img");
            img.src = notif.snapshot_url;
            img.className = "thumbnail-img";
            img.style.marginTop = "8px";
            img.onclick = () => {
                window.open(notif.snapshot_url, "_blank");
            };
            toast.querySelector(".toast-content").appendChild(img);
        }

        this.toastContainer.appendChild(toast);

        // Auto remove after 8 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.style.opacity = "0";
                toast.style.transition = "opacity 0.4s ease";
                setTimeout(() => toast.remove(), 400);
            }
        }, 8000);
    }

    showThreatModal(notif) {
        const modal = document.getElementById("threat-alert-modal");
        const body = document.getElementById("threat-modal-body");
        if (!modal || !body) return;

        this.currentThreatNotifId = notif.id;
        this.currentThreatEventId = notif.event_id || null;

        let snapHtml = "";
        if (notif.snapshot_url) {
            snapHtml = `
                <div style="background: #000; border-radius: 8px; overflow: hidden; margin-bottom: 16px; border: 1px solid var(--border-color); text-align: center;">
                    <img src="${notif.snapshot_url}" alt="Threat Snapshot" style="max-height: 380px; max-width: 100%; object-fit: contain;">
                </div>
            `;
        }

        body.innerHTML = `
            ${snapHtml}
            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 16px; margin-bottom: 14px;">
                <h3 style="color: #f87171; font-size: 16px; margin-bottom: 6px; display: flex; align-items: center; gap: 8px;">
                    <span>⚠️</span> ${escapeHTML(notif.title)}
                </h3>
                <p style="color: #f0f6fc; font-size: 13.5px; line-height: 1.5;">${escapeHTML(notif.message)}</p>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 12.5px;">
                <div style="background: rgba(10, 14, 23, 0.6); padding: 10px 14px; border-radius: 6px; border: 1px solid var(--border-color);">
                    <span style="color: var(--text-muted);">Timestamp:</span>
                    <strong style="color: #fff; font-family: var(--font-mono); margin-left: 6px;">${notif.time || 'Immediate'}</strong>
                </div>
                <div style="background: rgba(10, 14, 23, 0.6); padding: 10px 14px; border-radius: 6px; border: 1px solid var(--border-color);">
                    <span style="color: var(--text-muted);">Classification:</span>
                    <strong style="color: #ef4444; margin-left: 6px;">${notif.category || 'THREAT'}</strong>
                </div>
            </div>
        `;

        const viewEventBtn = document.getElementById("btn-threat-view-event");
        if (viewEventBtn) {
            viewEventBtn.style.display = this.currentThreatEventId ? "inline-flex" : "none";
        }

        modal.classList.add("show");
    }

    updateUnreadCount(delta = 1) {
        const navBadge = document.getElementById("nav-unread-badge");
        const topBadge = document.getElementById("top-unread-badge");

        [navBadge, topBadge].forEach(badge => {
            if (badge) {
                let current = parseInt(badge.textContent || "0");
                current = Math.max(0, current + delta);
                badge.textContent = current;
                badge.style.display = current > 0 ? "inline-block" : "none";
            }
        });
    }
}

function closeThreatModal() {
    const modal = document.getElementById("threat-alert-modal");
    if (modal) modal.classList.remove("show");
}

function acknowledgeThreatAlert() {
    if (window.notificationEngine && window.notificationEngine.currentThreatNotifId) {
        const notifId = window.notificationEngine.currentThreatNotifId;
        fetch(`/api/notifications/${notifId}/acknowledge`, { method: "POST" })
            .then(res => res.json())
            .then(() => {
                closeThreatModal();
                if (window.notificationEngine) {
                    window.notificationEngine.updateUnreadCount(-1);
                }
            })
            .catch(() => closeThreatModal());
    } else {
        closeThreatModal();
    }
}

function viewThreatEvent() {
    if (window.notificationEngine && window.notificationEngine.currentThreatEventId) {
        window.location.href = `/events/${window.notificationEngine.currentThreatEventId}`;
    }
}

function escapeHTML(str) {
    if (!str) return "";
    return String(str).replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

// Instantiate engine when DOM ready
document.addEventListener("DOMContentLoaded", () => {
    window.notificationEngine = new NotificationEngine();
});
