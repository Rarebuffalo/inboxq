/**
 * InboxIQ Dashboard Client Application
 * Standardizes AJAX fetching, state synchronization, Chart.js graphs rendering,
 * overrides save commits, timeline audit lists, explainable AI logs, and CSV exporting.
 */

class InboxIQApp {
    constructor() {
        // App states
        this.tickets = [];
        this.activeTicket = null;
        this.stats = null;
        this.charts = {};
        
        // Pagination state
        this.currentPage = 1;
        this.pageSize = 10;
        
        // DOM binding
        this.cacheDOM();
        this.initializeTheme();
        this.bindEvents();
        
        // Initial data pull
        this.refreshAll();
        
        // Webhook check interval loop
        setInterval(() => this.pollAlerts(), 8000);
    }

    cacheDOM() {
        this.themeToggleBtn = document.getElementById("theme-toggle");
        this.btnRefresh = document.getElementById("refresh-queue");
        this.btnExportCSV = document.getElementById("btn-export-csv");
        
        // Filter elements
        this.inputSearch = document.getElementById("queue-search");
        this.selectPriority = document.getElementById("filter-priority");
        this.selectCategory = document.getElementById("filter-category");
        this.selectStatus = document.getElementById("filter-status");
        this.selectSortBy = document.getElementById("sort-by");
        this.selectSortOrder = document.getElementById("sort-order");
        
        // Ticket list elements
        this.listContainer = document.getElementById("ticket-list-container");
        this.detailContainer = document.getElementById("detail-panel-container");
        
        // Pagination buttons
        this.btnPrev = document.getElementById("btn-prev");
        this.btnNext = document.getElementById("btn-next");
        this.pageIndicator = document.getElementById("page-indicator");
        
        // Alert banner
        this.alertBanner = document.getElementById("escalation-alert-banner");
    }

    initializeTheme() {
        const theme = localStorage.getItem("color-scheme") || "dark";
        document.documentElement.setAttribute("data-theme", theme);
    }

    toggleTheme() {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("color-scheme", next);
    }

    bindEvents() {
        if (this.themeToggleBtn) {
            this.themeToggleBtn.addEventListener("click", () => this.toggleTheme());
        }
        
        // Filters reload trigger
        const triggers = [
            this.selectPriority, 
            this.selectCategory, 
            this.selectStatus, 
            this.selectSortBy, 
            this.selectSortOrder
        ];
        triggers.forEach(el => {
            if (el) el.addEventListener("change", () => {
                this.currentPage = 1;
                this.fetchQueue();
            });
        });
        
        // Search trigger with debounce
        let searchTimeout;
        if (this.inputSearch) {
            this.inputSearch.addEventListener("input", () => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.currentPage = 1;
                    this.fetchQueue();
                }, 300);
            });
        }
        
        // Refresh trigger
        if (this.btnRefresh) {
            this.btnRefresh.addEventListener("click", () => this.refreshAll());
        }
        
        // Export CSV trigger
        if (this.btnExportCSV) {
            this.btnExportCSV.addEventListener("click", () => this.exportCSV());
        }
        
        // Pagination triggers
        if (this.btnPrev) {
            this.btnPrev.addEventListener("click", () => {
                if (this.currentPage > 1) {
                    this.currentPage--;
                    this.fetchQueue();
                }
            });
        }
        if (this.btnNext) {
            this.btnNext.addEventListener("click", () => {
                this.currentPage++;
                this.fetchQueue();
            });
        }
    }

    // Refresh data elements
    refreshAll() {
        this.fetchAnalytics();
        this.fetchQueue();
        this.showToast("Operational status updated.");
    }

    // Export current queue to CSV
    exportCSV() {
        const search = this.inputSearch.value.trim();
        const priority = this.selectPriority.value;
        const category = this.selectCategory.value;
        const status = this.selectStatus.value;
        
        let url = `/api/v1/tickets/export?`;
        if (search) url += `search=${encodeURIComponent(search)}&`;
        if (priority) url += `priority=${priority}&`;
        if (category) url += `category=${category}&`;
        if (status) url += `status=${status}&`;
        
        window.location.href = url;
        this.showToast("CSV export downloaded.");
    }

    // Toast notification alerts
    showToast(message, type = "info") {
        const container = document.getElementById("toast-container");
        if (!container) return;
        
        const toast = document.createElement("div");
        toast.className = `toast ${type === "warning" ? "toast-warning" : ""}`;
        toast.textContent = message;
        
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    }

    // Fetch analytical aggregates
    async fetchAnalytics() {
        try {
            const res = await fetch("/api/v1/analytics/stats");
            if (!res.ok) throw new Error("Stats fetch failed");
            this.stats = await res.json();
            if (this.stats) {
                this.renderStats();
                this.renderCharts();
            }
        } catch (err) {
            console.error("Error loading aggregates: ", err);
        }
    }

    // Periodic check for P0/P1 active alerts
    async pollAlerts() {
        try {
            const res = await fetch("/api/v1/analytics/stats");
            if (!res.ok) return;
            const data = await res.json();
            const openCriticals = data.p0_count + data.p1_count;
            
            if (openCriticals > 0) {
                this.alertBanner.classList.remove("hidden");
            } else {
                this.alertBanner.classList.add("hidden");
            }
        } catch (e) {
            console.error("Alert poll failed: ", e);
        }
    }

    renderStats() {
        document.getElementById("val-total").textContent = this.stats.total_tickets;
        document.getElementById("val-p0").textContent = this.stats.p0_count;
        document.getElementById("val-p1").textContent = this.stats.p1_count;
        
        const statusMap = this.stats.by_status || {};
        document.getElementById("val-open").textContent = statusMap.open || 0;
        document.getElementById("val-investigating").textContent = statusMap.investigating || 0;
        document.getElementById("val-resolved").textContent = statusMap.resolved || 0;
        
        document.getElementById("val-today").textContent = this.stats.tickets_today;
        document.getElementById("val-confidence").textContent = `${Math.round(this.stats.average_confidence * 100)}%`;
        
        // Toggle warning banner
        const openCriticals = this.stats.p0_count + this.stats.p1_count;
        if (openCriticals > 0) {
            this.alertBanner.classList.remove("hidden");
        } else {
            this.alertBanner.classList.add("hidden");
        }
    }

    renderCharts() {
        this.renderPriorityChart();
        this.renderCategoryChart();
        this.renderStatusChart();
        this.renderActivityChart();
    }

    destroyChart(key) {
        if (this.charts[key]) {
            this.charts[key].destroy();
        }
    }

    renderPriorityChart() {
        this.destroyChart("priority");
        const ctx = document.getElementById("chart-priority").getContext("2d");
        
        const labels = ["Critical (P0)", "High (P1)", "Medium (P2)", "Low (P3)"];
        const data = [
            this.stats.by_priority.P0 || 0,
            this.stats.by_priority.P1 || 0,
            this.stats.by_priority.P2 || 0,
            this.stats.by_priority.P3 || 0
        ];
        
        this.charts.priority = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Count',
                    data,
                    backgroundColor: ['#f43f5e', '#fb923c', '#fbbf24', '#34d399'],
                    borderWidth: 0,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#8da2c0' } },
                    y: { grid: { color: '#2b3d5a' }, ticks: { precision: 0, color: '#8da2c0' } }
                }
            }
        });
    }

    renderCategoryChart() {
        this.destroyChart("category");
        const ctx = document.getElementById("chart-category").getContext("2d");
        
        const categories = {
            security_emergency: "Security",
            access_issue: "Access",
            onboarding_kyc: "KYC",
            billing_payment: "Billing",
            locker_management: "Lockers",
            general_support: "General"
        };
        
        const labels = Object.values(categories);
        const data = Object.keys(categories).map(key => this.stats.by_category[key] || 0);
        
        this.charts.category = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data,
                    backgroundColor: ['#f43f5e', '#a855f7', '#60a5fa', '#3b82f6', '#fb923c', '#9ca3af'],
                    borderWidth: 2,
                    borderColor: '#151f32'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { color: '#8da2c0', boxWidth: 12, font: { size: 10 } }
                    }
                }
            }
        });
    }

    renderStatusChart() {
        this.destroyChart("status");
        const ctx = document.getElementById("chart-status").getContext("2d");
        
        const labels = ["Open", "Investigating", "Resolved"];
        const data = [
            this.stats.by_status.open || 0,
            this.stats.by_status.investigating || 0,
            this.stats.by_status.resolved || 0
        ];
        
        this.charts.status = new Chart(ctx, {
            type: 'polarArea',
            data: {
                labels,
                datasets: [{
                    data,
                    backgroundColor: ['rgba(244, 63, 94, 0.4)', 'rgba(96, 165, 250, 0.4)', 'rgba(52, 211, 153, 0.4)'],
                    borderColor: '#151f32',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { color: '#8da2c0', boxWidth: 12, font: { size: 10 } }
                    }
                },
                scales: {
                    r: { grid: { color: '#2b3d5a' }, ticks: { color: '#8da2c0', backdropColor: 'transparent' } }
                }
            }
        });
    }

    renderActivityChart() {
        this.destroyChart("activity");
        const ctx = document.getElementById("chart-activity").getContext("2d");
        
        const labels = [];
        for (let i = 4; i >= 0; i--) {
            const d = new Date();
            d.setDate(d.getDate() - i);
            labels.push(d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }));
        }
        
        const mockActivity = [6, 12, 18, 9, this.stats.tickets_today];
        
        this.charts.activity = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Tickets',
                    data: mockActivity,
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#8da2c0' } },
                    y: { grid: { color: '#2b3d5a' }, ticks: { precision: 0, color: '#8da2c0' } }
                }
            }
        });
    }

    async fetchQueue() {
        try {
            const skip = (this.currentPage - 1) * this.pageSize;
            const search = this.inputSearch.value.trim();
            const priority = this.selectPriority.value;
            const category = this.selectCategory.value;
            const status = this.selectStatus.value;
            const sort_by = this.selectSortBy.value;
            const sort_order = this.selectSortOrder.value;
            
            let url = `/api/v1/tickets?skip=${skip}&limit=${this.pageSize + 1}&sort_by=${sort_by}&sort_order=${sort_order}`;
            if (search) url += `&search=${encodeURIComponent(search)}`;
            if (priority) url += `&priority=${priority}`;
            if (category) url += `&category=${category}`;
            if (status) url += `&status=${status}`;
            
            const res = await fetch(url);
            if (!res.ok) throw new Error("Failed to load queue list");
            
            const results = await res.json();
            
            if (results.length > this.pageSize) {
                this.btnNext.disabled = false;
                this.tickets = results.slice(0, this.pageSize);
            } else {
                this.btnNext.disabled = true;
                this.tickets = results;
            }
            
            this.btnPrev.disabled = this.currentPage === 1;
            this.pageIndicator.textContent = `Page ${this.currentPage}`;
            
            this.renderQueue();
        } catch (err) {
            console.error("Queue loader error: ", err);
            this.listContainer.innerHTML = `<p class="empty-message error-message">Failed to load support queue.</p>`;
        }
    }

    renderQueue() {
        if (this.tickets.length === 0) {
            this.listContainer.innerHTML = `<p class="empty-message">No matching tickets found.</p>`;
            return;
        }
        
        this.listContainer.innerHTML = "";
        this.tickets.forEach(ticket => {
            const item = document.createElement("div");
            item.className = `ticket-item ${this.activeTicket && this.activeTicket.id === ticket.id ? "active" : ""}`;
            item.innerHTML = `
                <div class="ticket-item-header">
                    <span class="ticket-email">${ticket.email_id}</span>
                    <span class="ticket-time">${this.formatDate(ticket.created_at)}</span>
                </div>
                <div class="ticket-title">
                    <span style="color:var(--text-secondary); font-family:monospace; font-size:0.75rem; font-weight:700;">${ticket.ticket_code}</span> ${ticket.title}
                </div>
                <div class="ticket-meta-footer">
                    <span class="badge badge-${ticket.priority.toLowerCase()}">${ticket.priority}</span>
                    <span class="badge badge-status-${ticket.status.toLowerCase()}">${ticket.status}</span>
                    <span class="badge badge-source">${ticket.classification_source}</span>
                </div>
            `;
            
            item.addEventListener("click", () => this.selectTicket(ticket.id));
            this.listContainer.appendChild(item);
        });
    }

    formatDate(isoString) {
        if (!isoString) return "-";
        const d = new Date(isoString);
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    async selectTicket(id) {
        try {
            const res = await fetch(`/api/v1/tickets/${id}`);
            if (!res.ok) throw new Error("Failed to pull details");
            this.activeTicket = await res.json();
            
            this.renderQueue();
            this.renderDetails();
        } catch (e) {
            console.error("Detail pulling error: ", e);
            this.showToast("Could not pull ticket details.", "warning");
        }
    }

    // Detail Panel Renderer
    renderDetails() {
        const t = this.activeTicket;
        if (!t) return;
        
        let escalationHtml = "";
        if (t.priority === "P0" || t.priority === "P1") {
            escalationHtml = `
                <div class="escalation-box">
                    <div class="escalation-title">Simulated Webhook Alert Logged</div>
                    <div class="escalation-desc">
                        <strong>Escalation Target:</strong> Paged Emergency Operations Center (EOC).<br>
                        <strong>Suggested action checklist:</strong> "${t.suggested_action}".
                    </div>
                </div>
            `;
        }
        
        // Manual review flagged banner
        let reviewBannerHtml = "";
        if (t.needs_manual_review) {
            reviewBannerHtml = `
                <div class="escalation-box" style="background-color:rgba(251, 191, 36, 0.08); border-color:var(--color-p2); color:var(--color-p2);">
                    <div class="escalation-title" style="color:var(--color-p2);">⚠️ Flagged for Manual Review</div>
                    <div class="escalation-desc">AI classification confidence was below the 60% threshold. Verify category and priority mappings.</div>
                </div>
            `;
        }

        // SLA Overdue calculation
        const now = new Date();
        const deadline = new Date(t.sla_deadline);
        const isOverdue = now > deadline && t.status !== "resolved";
        const slaText = `${this.formatDate(t.sla_deadline)} ${isOverdue ? '<span style="color:var(--color-p0); font-weight:700;">(OVERDUE)</span>' : ''}`;

        // Timeline events map
        let timelineEventsHtml = "";
        if (t.timeline && t.timeline.length > 0) {
            timelineEventsHtml = t.timeline.map(ev => `
                <li class="timeline-event">
                    <span class="timeline-time">${this.formatDate(ev.created_at)}</span>
                    <span class="timeline-badge">${ev.event_type.toUpperCase()}</span>
                    <span class="timeline-desc">${ev.description}</span>
                </li>
            `).join("");
        } else {
            timelineEventsHtml = `<li class="timeline-event">No events logged.</li>`;
        }
        
        this.detailContainer.innerHTML = `
            <div class="detail-header">
                <div class="detail-header-top">
                    <h2><span style="font-family:monospace; color:var(--text-secondary); font-size:1.15rem; display:block;">${t.ticket_code}</span>${t.title}</h2>
                    <span class="badge badge-${t.priority.toLowerCase()}">${t.priority}</span>
                </div>
                <div class="detail-email">From: <strong>${t.email_id}</strong></div>
            </div>
            
            ${reviewBannerHtml}
            ${escalationHtml}
            
            <div class="detail-text-block">
                <h3>Original Email Content</h3>
                <div class="detail-content">${t.body}</div>
            </div>
            
            <div class="detail-grid">
                <div class="detail-field">
                    <label>Summary</label>
                    <span>${t.summary}</span>
                </div>
                <div class="detail-field">
                    <label>AI Reason</label>
                    <span>${t.reasoning}</span>
                </div>
                <div class="detail-field">
                    <label>Confidence</label>
                    <span>${Math.round(t.confidence * 100)}%</span>
                </div>
                <div class="detail-field">
                    <label>Classification Origin</label>
                    <span>${t.classification_source.toUpperCase()}</span>
                </div>
                <div class="detail-field">
                    <label>Allocated Queue</label>
                    <span>${t.queue_name}</span>
                </div>
                <div class="detail-field">
                    <label>SLA Target</label>
                    <span>${slaText}</span>
                </div>
            </div>

            <!-- Explainable AI Logs -->
            <div class="detail-text-block">
                <h3>Explainable AI - Token Matching Analysis</h3>
                <div class="detail-content" style="font-family:monospace; font-size:0.8rem; background-color:#070a12; border-color:#1c293f; max-height:100px;">${t.explainable_ai ? t.explainable_ai.replace(/\n/g, '<br>') : 'No token signals tracked.'}</div>
            </div>

            <!-- Timeline history -->
            <div class="detail-text-block">
                <h3>Lifecycle Timeline Logs</h3>
                <ul class="timeline-list">
                    ${timelineEventsHtml}
                </ul>
            </div>
            
            <div class="overrides-section">
                <h3>Manual Operational Overrides</h3>
                <div class="overrides-grid">
                    <div class="overrides-field">
                        <label for="override-category">Category</label>
                        <select id="override-category">
                            <option value="security_emergency" ${t.category === 'security_emergency' ? 'selected' : ''}>Security / Emergency</option>
                            <option value="access_issue" ${t.category === 'access_issue' ? 'selected' : ''}>Access Issue</option>
                            <option value="onboarding_kyc" ${t.category === 'onboarding_kyc' ? 'selected' : ''}>Onboarding & KYC</option>
                            <option value="billing_payment" ${t.category === 'billing_payment' ? 'selected' : ''}>Billing & Payment</option>
                            <option value="locker_management" ${t.category === 'locker_management' ? 'selected' : ''}>Locker Management</option>
                            <option value="general_support" ${t.category === 'general_support' ? 'selected' : ''}>General Support</option>
                        </select>
                    </div>
                    <div class="overrides-field">
                        <label for="override-priority">Priority</label>
                        <select id="override-priority">
                            <option value="P0" ${t.priority === 'P0' ? 'selected' : ''}>P0 - Critical</option>
                            <option value="P1" ${t.priority === 'P1' ? 'selected' : ''}>P1 - High</option>
                            <option value="P2" ${t.priority === 'P2' ? 'selected' : ''}>P2 - Medium</option>
                            <option value="P3" ${t.priority === 'P3' ? 'selected' : ''}>P3 - Low</option>
                        </select>
                    </div>
                    <div class="overrides-field">
                        <label for="override-status">Status</label>
                        <select id="override-status">
                            <option value="open" ${t.status === 'open' ? 'selected' : ''}>Open</option>
                            <option value="investigating" ${t.status === 'investigating' ? 'selected' : ''}>Investigating</option>
                            <option value="resolved" ${t.status === 'resolved' ? 'selected' : ''}>Resolved</option>
                        </select>
                    </div>
                    <div class="overrides-field">
                        <label for="override-assignee">Assigned Agent</label>
                        <input type="text" id="override-assignee" value="${t.assigned_to || ''}" placeholder="Unassigned">
                    </div>
                </div>
                
                <div class="draft-editor">
                    <label for="override-draft" style="display:block; font-size:0.75rem; font-weight:700; color:var(--text-secondary); text-transform:uppercase; margin-bottom:0.25rem;">Draft Reply</label>
                    <textarea id="override-draft">${t.draft_reply}</textarea>
                </div>
                
                <div class="actions-row">
                    <button id="btn-save-override" class="btn btn-primary">Save Changes</button>
                    <button id="btn-send-reply" class="btn btn-secondary">Send Draft Reply (Simulation)</button>
                </div>
            </div>
        `;
        
        // Bind override save event
        document.getElementById("btn-save-override").addEventListener("click", () => this.saveOverrides());
        document.getElementById("btn-send-reply").addEventListener("click", () => this.sendDraftSimulation());
    }

    async saveOverrides() {
        if (!this.activeTicket) return;
        
        const category = document.getElementById("override-category").value;
        const priority = document.getElementById("override-priority").value;
        const status = document.getElementById("override-status").value;
        const assigned_to = document.getElementById("override-assignee").value.trim() || null;
        const draft_reply = document.getElementById("override-draft").value;
        
        try {
            const res = await fetch(`/api/v1/tickets/${this.activeTicket.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category, priority, status, assigned_to, draft_reply })
            });
            
            if (!res.ok) throw new Error("Patch failed");
            
            this.activeTicket = await res.json();
            this.showToast(`Ticket ${this.activeTicket.ticket_code} updated successfully.`);
            
            // Reload states
            this.fetchAnalytics();
            this.fetchQueue();
            this.renderDetails();
        } catch (e) {
            console.error("Override commit error: ", e);
            this.showToast("Could not save override changes.", "warning");
        }
    }

    sendDraftSimulation() {
        if (!this.activeTicket) return;
        
        const recipient = this.activeTicket.email_id;
        this.showToast(`[SIMULATION] Email reply dispatched to ${recipient}.`);
        console.log(`[SIMULATED WEBHOOK ALERT] Dispatched response reply to: ${recipient}. Reply Body excerpt: "${document.getElementById("override-draft").value.substring(0, 80)}..."`);
    }
}

// Boot application dashboard
document.addEventListener("DOMContentLoaded", () => {
    window.InboxIQ = new InboxIQApp();
});
