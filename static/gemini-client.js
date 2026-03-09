/**
 * Gemini Smart Model Resolver v2.0 — Universal Client
 * 
 * Features:
 * 1. Pro / Fast toggle — switch between quality (pro) and speed (flash) modes
 * 2. Rate limit tracking — approximate daily quota counter with "try again" UI
 * 3. Smart model routing — automatic cascade on 429/503 errors
 * 4. Custom API Key support (localStorage) with secure server fallback
 * 5. Dynamic model discovery via /api/models
 * 6. Drop-in floating UI with searchable model dropdown
 * 
 * Config: Set window.GEMINI_CONFIG before loading this script to customize behavior.
 *   window.GEMINI_CONFIG = { needsRealTimeData: true }  // for projects needing search grounding
 */

const GEMINI_API_MODELS = "/api/models";
const GEMINI_API_GENERATE = "/api/chat";

// Published free-tier daily limits (Feb 2026)
const DAILY_LIMITS = {
    "pro": { "3.1": 50, "2.5": 25 },
    "flash": { "3.1": 500, "2.5": 250 },
    "flash-lite": { "3.1": 1000, "2.5": 500 }
};

// Known fallback cascades
const CASCADE_STATIC = [
    "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview",
    "gemini-2.5-pro", "gemini-2.5-flash"
];
const CASCADE_REALTIME = [
    "gemini-2.5-pro", "gemini-2.5-flash",
    "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview"
];

const MODEL_TIER_SCORES = { "pro": 100, "flash": 50, "flash-lite": 25, "lite": 25 };

class GeminiClient {
    constructor(apiKeyStorageKey = "gemini_api_key") {
        this.storageKey = apiKeyStorageKey;
        this.apiKey = localStorage.getItem(this.storageKey) || "";
        this.isUsingDefaultKey = !this.apiKey;
        this.availableModels = [];
        this.selectedModel = localStorage.getItem("gemini_selected_model") || "";

        // Pro/Fast mode
        this.mode = localStorage.getItem("gemini_mode") || "pro"; // "pro" | "fast"

        // Real-time data config
        const cfg = window.GEMINI_CONFIG || {};
        this.needsRealTimeData = cfg.needsRealTimeData || false;

        // Rate limit tracking
        this._initRateLimits();
    }

    // ─── Rate Limit Tracking ───
    _initRateLimits() {
        const stored = localStorage.getItem("gemini_rate_limits");
        const today = new Date().toISOString().slice(0, 10);

        if (stored) {
            const parsed = JSON.parse(stored);
            if (parsed.date === today) {
                this.rateLimits = parsed;
                return;
            }
        }
        // Reset counters for new day
        this.rateLimits = { date: today, used: {} };
        this._saveRateLimits();
    }

    _saveRateLimits() {
        localStorage.setItem("gemini_rate_limits", JSON.stringify(this.rateLimits));
    }

    _trackUsage(modelName) {
        const tier = this._getModelTier(modelName);
        if (!this.rateLimits.used[tier]) this.rateLimits.used[tier] = 0;
        this.rateLimits.used[tier]++;
        this._saveRateLimits();
        this._updateRateLimitUI();
    }

    _getModelTier(name) {
        const n = name.toLowerCase();
        if (n.includes("flash-lite")) return "flash-lite";
        if (n.includes("pro")) return "pro";
        if (n.includes("flash")) return "flash";
        return "other";
    }

    _getModelVersion(name) {
        const n = name.toLowerCase();
        if (n.includes("3.1") || n.includes("3.0")) return "3.1";
        if (n.includes("2.5") || n.includes("2.0")) return "2.5";
        return "3.1";
    }

    getRemainingRequests() {
        const tier = this.mode === "pro" ? "pro" : "flash-lite";
        const version = this.needsRealTimeData ? "2.5" : "3.1";
        const limit = DAILY_LIMITS[tier]?.[version] || 50;
        const used = this.rateLimits.used[tier] || 0;
        return Math.max(0, limit - used);
    }

    getDailyLimit() {
        const tier = this.mode === "pro" ? "pro" : "flash-lite";
        const version = this.needsRealTimeData ? "2.5" : "3.1";
        return DAILY_LIMITS[tier]?.[version] || 50;
    }

    // ─── Model Scoring ───
    _scoreModel(name) {
        let score = 0;
        const lowName = name.toLowerCase();

        if (lowName.includes("flash-lite")) score = MODEL_TIER_SCORES["flash-lite"];
        else if (lowName.includes("pro")) score = MODEL_TIER_SCORES["pro"];
        else if (lowName.includes("lite")) score = MODEL_TIER_SCORES["lite"];
        else if (lowName.includes("flash")) score = MODEL_TIER_SCORES["flash"];
        else score = 10;

        const vMatch = lowName.match(/(\d+)\.(\d+)/);
        let vScore = 1.0;
        if (vMatch) {
            vScore = parseInt(vMatch[1]) + (parseInt(vMatch[2]) * 0.1);
        } else if (lowName.match(/gemini-(\d+)-/)) {
            vScore = parseFloat(lowName.match(/gemini-(\d+)-/)[1]);
        } else if (lowName.includes("latest")) {
            vScore = 2.5;
        }

        score *= vScore;
        if (lowName.includes("preview")) score *= 1.05;
        if (lowName.includes("exp")) score *= 0.85;

        return Math.round(score * 100) / 100;
    }

    // ─── Smart Model Selection based on Mode ───
    getActiveModel() {
        if (this.availableModels.length === 0) {
            return this._getDefaultModel();
        }

        const isPro = this.mode === "pro";
        const models = this.availableModels;

        if (isPro) {
            // Find best pro model, prefer 2.5 for real-time, 3.1 for static
            const pros = models.filter(m => m.name.includes("pro"));
            if (this.needsRealTimeData) {
                const rt = pros.find(m => m.name.includes("2.5"));
                if (rt) return rt.name;
            } else {
                const st = pros.find(m => m.name.includes("3.1"));
                if (st) return st.name;
            }
            return pros[0]?.name || this._getDefaultModel();
        } else {
            // Fast mode — find best flash/flash-lite
            const flashes = models.filter(m => m.name.includes("flash"));
            if (this.needsRealTimeData) {
                const rt = flashes.find(m => m.name.includes("2.5"));
                if (rt) return rt.name;
            } else {
                const st = flashes.find(m => m.name.includes("3.1"));
                if (st) return st.name;
            }
            return flashes[0]?.name || this._getDefaultModel();
        }
    }

    _getDefaultModel() {
        if (this.needsRealTimeData) {
            return this.mode === "pro" ? "gemini-2.5-pro" : "gemini-2.5-flash";
        }
        return this.mode === "pro" ? "gemini-3.1-pro-preview" : "gemini-3.1-flash-lite-preview";
    }

    // ─── Model Discovery ───
    async discoverModels() {
        try {
            const headers = {};
            if (this.apiKey) headers["x-gemini-api-key"] = this.apiKey;

            const response = await fetch(GEMINI_API_MODELS, { headers });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error?.message || "Failed to fetch models");
            }

            const data = await response.json();

            const contentModels = data.models.filter(m =>
                m.supportedGenerationMethods &&
                m.supportedGenerationMethods.includes("generateContent")
            ).map(m => {
                const cleanName = m.name.replace("models/", "");
                return {
                    name: cleanName,
                    displayName: m.displayName || cleanName,
                    description: m.description,
                    score: this._scoreModel(cleanName)
                };
            });

            contentModels.sort((a, b) => b.score - a.score);
            this.availableModels = contentModels;

            // Auto-select based on mode
            this.selectedModel = this.getActiveModel();
            localStorage.setItem("gemini_selected_model", this.selectedModel);

            return this.availableModels;
        } catch (error) {
            console.error("Gemini API Model Discovery Failed:", error);
            const fallback = this.needsRealTimeData ? CASCADE_REALTIME : CASCADE_STATIC;
            this.availableModels = fallback.map(name => ({
                name, displayName: name, description: "Fallback model",
                score: this._scoreModel(name)
            }));
            if (!this.selectedModel) this.selectedModel = this._getDefaultModel();
            return this.availableModels;
        }
    }

    // ─── Generation ───
    async generateContent(promptText, systemInstruction = null) {
        if (!this.selectedModel) this.selectedModel = this.getActiveModel();

        const remaining = this.getRemainingRequests();
        if (remaining <= 0) {
            this._showRateLimitBanner();
            throw new Error("Daily rate limit reached. Try again tomorrow or switch to Fast mode for higher limits.");
        }

        const payload = {
            contents: [{ parts: [{ text: promptText }] }],
            model: this.selectedModel
        };

        if (systemInstruction) {
            payload.systemInstruction = { parts: [{ text: systemInstruction }] };
        }

        const headers = { 'Content-Type': 'application/json' };
        if (this.apiKey) headers["x-gemini-api-key"] = this.apiKey;

        const response = await fetch(GEMINI_API_GENERATE, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            if (response.status === 429) {
                this._showRateLimitBanner();
                throw new Error("⏳ Rate limit reached — try again in ~1 minute, or switch to Fast mode.");
            }
            throw new Error(`Gemini API Error (${response.status}): ${err.error?.message || "Unknown error"}`);
        }

        const data = await response.json();
        const modelUsed = data._model_used || this.selectedModel;
        this._trackUsage(modelUsed);

        // Update UI to show which model actually responded
        this._updateModelUsedBadge(modelUsed);

        return data.candidates?.[0]?.content?.parts?.[0]?.text || "";
    }

    // ─── Mode Toggle ───
    setMode(mode) {
        this.mode = mode;
        localStorage.setItem("gemini_mode", mode);
        this.selectedModel = this.getActiveModel();
        localStorage.setItem("gemini_selected_model", this.selectedModel);
        this._updateModeUI();
        this._updateRateLimitUI();
    }

    toggleMode() {
        this.setMode(this.mode === "pro" ? "fast" : "pro");
    }

    setApiKey(key) {
        this.apiKey = key.trim();
        localStorage.setItem(this.storageKey, this.apiKey);
        this.isUsingDefaultKey = !this.apiKey;
    }

    getApiKey() { return this.apiKey; }
    hasApiKey() { return true; }

    // ─── Rate Limit Banner ───
    _showRateLimitBanner() {
        let banner = document.getElementById("gemini-rate-banner");
        if (!banner) {
            banner = document.createElement("div");
            banner.id = "gemini-rate-banner";
            banner.style.cssText = `
                position: fixed; top: 0; left: 0; right: 0; z-index: 99999;
                background: linear-gradient(135deg, #dc2626, #b91c1c); color: white;
                padding: 12px 20px; text-align: center; font-family: system-ui;
                font-size: 14px; font-weight: 500; display: flex; align-items: center;
                justify-content: center; gap: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            `;
            document.body.prepend(banner);
        }
        const remaining = this.getRemainingRequests();
        banner.innerHTML = `
            ⏳ Rate limit reached (${remaining} ${this.mode === "pro" ? "Pro" : "Fast"} requests remaining today)
            <button onclick="window.gemini.setMode('${this.mode === "pro" ? "fast" : "pro"}'); this.parentElement.remove();"
                style="background: white; color: #dc2626; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 12px;">
                Switch to ${this.mode === "pro" ? "Fast 🚀" : "Pro ⚡"}
            </button>
            <button onclick="this.parentElement.remove();"
                style="background: transparent; color: white; border: 1px solid rgba(255,255,255,0.3); padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 12px;">
                ✕
            </button>
        `;
        // Auto-dismiss after 10s
        setTimeout(() => { if (banner.parentElement) banner.remove(); }, 10000);
    }

    _updateModelUsedBadge(modelName) {
        const badge = document.getElementById("gemini-model-used");
        if (badge) {
            const tier = this._getModelTier(modelName);
            const short = modelName.replace("gemini-", "").replace("-preview", "");
            badge.textContent = short;
            badge.style.background = tier === "pro" ? "rgba(139,92,246,0.2)" : "rgba(16,185,129,0.2)";
            badge.style.color = tier === "pro" ? "#a78bfa" : "#34d399";
        }
    }

    _updateModeUI() {
        const toggle = document.getElementById("gemini-mode-toggle");
        if (toggle) {
            const isPro = this.mode === "pro";
            toggle.innerHTML = isPro ? "⚡ PRO" : "🚀 FAST";
            toggle.style.background = isPro
                ? "linear-gradient(135deg, #7c3aed, #6d28d9)"
                : "linear-gradient(135deg, #059669, #047857)";
        }
        const searchInput = document.getElementById("gemini-search-input");
        if (searchInput) searchInput.value = this.selectedModel;
    }

    _updateRateLimitUI() {
        const el = document.getElementById("gemini-quota-display");
        if (el) {
            const remaining = this.getRemainingRequests();
            const limit = this.getDailyLimit();
            const pct = Math.round((remaining / limit) * 100);
            const color = pct > 50 ? "#10b981" : pct > 20 ? "#f59e0b" : "#ef4444";
            el.innerHTML = `
                <div style="display:flex; align-items:center; gap:6px;">
                    <div style="flex:1; height:4px; background:rgba(255,255,255,0.1); border-radius:2px; overflow:hidden;">
                        <div style="width:${pct}%; height:100%; background:${color}; border-radius:2px; transition:width 0.3s;"></div>
                    </div>
                    <span style="font-size:11px; color:${color}; white-space:nowrap;">~${remaining}/${limit}</span>
                </div>
            `;
        }
    }

    // ─── Floating UI ───
    injectUI(containerId = null) {
        const container = containerId ? document.getElementById(containerId) : document.body;
        if (!container) return;
        if (document.getElementById("gemini-client-ui-container")) return;

        const isPro = this.mode === "pro";
        const uiHtml = `
            <div id="gemini-client-ui-container" style="position: fixed; bottom: 20px; right: 20px; z-index: 9999; font-family: system-ui, -apple-system, sans-serif;">
                <style>
                    #gemini-floating-btn {
                        width: 50px; height: 50px; border-radius: 50%; background: #1e293b; 
                        border: 2px solid #334155; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                        cursor: pointer; display: flex; align-items: center; justify-content: center;
                        transition: all 0.2s; position: absolute; bottom: 0; right: 0;
                        color: white; z-index: 10000;
                    }
                    #gemini-floating-btn:hover { transform: scale(1.05); border-color: #3b82f6; }
                    
                    #gemini-client-ui {
                        position: absolute; bottom: 60px; right: 0;
                        background: rgba(15, 23, 42, 0.97); backdrop-filter: blur(12px);
                        border: 1px solid rgba(255,255,255,0.1); border-radius: 14px;
                        padding: 18px; color: #f1f5f9; box-shadow: 0 10px 30px rgba(0,0,0,0.6);
                        width: 300px; display: none; flex-direction: column; opacity: 0;
                        transition: opacity 0.2s;
                    }
                    #gemini-client-ui.show { display: flex; opacity: 1; }
                    
                    #gemini-client-ui input, #gemini-client-ui select {
                        width: 100%; box-sizing: border-box; background: rgba(0,0,0,0.3); 
                        border: 1px solid rgba(255,255,255,0.15); color: white; padding: 8px 10px; 
                        border-radius: 8px; margin-top: 6px; font-size: 13px; outline:none;
                    }
                    #gemini-client-ui input:focus { border-color: #3b82f6; }
                    #gemini-client-ui button.save-btn {
                        width: 100%; margin-top: 12px; padding: 9px;
                        background: #3b82f6; border: none; color: white;
                        border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px;
                    }
                    #gemini-client-ui button.save-btn:hover { background: #2563eb; }
                    #gemini-status { font-size: 12px; margin-top: 8px; color: #94a3b8; }
                    
                    .gemini-dropdown { position: relative; margin-top: 6px; }
                    .gemini-dropdown-input { width: 100%; padding: 8px 10px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.15); color: white; border-radius: 8px; outline:none; font-size:13px;}
                    .gemini-dropdown-list { 
                        position: absolute; top: 100%; left: 0; right: 0; background: #1e293b; 
                        border: 1px solid #334155; border-radius: 8px; max-height: 150px; overflow-y: auto; 
                        display: none; z-index: 100; margin-top:4px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                    }
                    .gemini-dropdown-list.show { display: block; }
                    .gemini-dropdown-item { padding: 8px 10px; font-size: 12px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05); }
                    .gemini-dropdown-item:hover { background: #3b82f6; }
                    
                    #gemini-mode-toggle {
                        padding: 5px 14px; border: none; border-radius: 20px; cursor: pointer;
                        font-weight: 700; font-size: 12px; color: white; transition: all 0.2s;
                        letter-spacing: 0.5px;
                    }
                    #gemini-mode-toggle:hover { filter: brightness(1.15); transform: scale(1.05); }
                </style>
                
                <div id="gemini-floating-btn" title="AI Configuration">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                </div>

                <div id="gemini-client-ui">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                        <div style="font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 6px;">
                            ✨ Gemini Engine
                            <span id="gemini-key-indicator" style="width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></span>
                        </div>
                        <button id="gemini-mode-toggle" style="background: ${isPro ? 'linear-gradient(135deg, #7c3aed, #6d28d9)' : 'linear-gradient(135deg, #059669, #047857)'}">
                            ${isPro ? '⚡ PRO' : '🚀 FAST'}
                        </button>
                    </div>

                    <!-- Model Used Badge -->
                    <div style="display:flex; align-items:center; gap:6px; margin-bottom:10px;">
                        <span style="font-size:10px; color:#64748b;">Active:</span>
                        <span id="gemini-model-used" style="font-size:11px; padding:2px 8px; border-radius:10px; background:rgba(139,92,246,0.2); color:#a78bfa;">${this.selectedModel ? this.selectedModel.replace('gemini-', '').replace('-preview', '') : '...'}</span>
                    </div>

                    <!-- Rate Limit Display -->
                    <div id="gemini-quota-display" style="margin-bottom: 12px;"></div>
                    
                    <div>
                        <label style="font-size: 11px; color: #94a3b8; display: block; margin-bottom: 2px;">API Key</label>
                        <input type="password" id="gemini-ui-key" placeholder="${this.isUsingDefaultKey ? 'Using Secure Server Key' : 'AIza...'}" value="${this.isUsingDefaultKey ? '' : '••••••••'}">
                        <div style="font-size: 10px; color: #475569; margin-top: 6px; line-height: 1.4;">
                            Leave blank for default free key.
                            <a href="https://aistudio.google.com/app/apikey" target="_blank" style="color: #3b82f6; text-decoration: none;"> Get your own →</a>
                        </div>
                    </div>
    
                    <div style="margin-top: 12px;">
                        <label style="font-size: 11px; color: #94a3b8;">Model</label>
                        <div class="gemini-dropdown">
                            <input type="text" id="gemini-search-input" class="gemini-dropdown-input" placeholder="Search models..." value="${this.selectedModel}">
                            <div id="gemini-dropdown-list" class="gemini-dropdown-list"></div>
                        </div>
                    </div>
                    
                    <button id="gemini-ui-save" class="save-btn">Save & Connect</button>
                    <div id="gemini-status"></div>
                </div>
            </div>
        `;

        container.insertAdjacentHTML('beforeend', uiHtml);

        const btn = document.getElementById('gemini-floating-btn');
        const panel = document.getElementById('gemini-client-ui');
        const searchInput = document.getElementById('gemini-search-input');
        const listDiv = document.getElementById('gemini-dropdown-list');

        // Toggle Panel
        btn.addEventListener('click', () => {
            panel.classList.toggle('show');
            if (panel.classList.contains('show') && this.availableModels.length === 0) {
                document.getElementById('gemini-status').innerHTML = "Fetching models...";
                this.discoverModels().then(models => {
                    this._populateDropdownUI(models);
                    document.getElementById('gemini-status').innerHTML = `<span style="color:#10b981">Found ${models.length} models.</span>`;
                }).catch(err => {
                    document.getElementById('gemini-status').innerHTML = `<span style="color:#ef4444">${err.message}</span>`;
                });
            }
        });

        // Mode Toggle
        document.getElementById('gemini-mode-toggle').addEventListener('click', () => {
            this.toggleMode();
            if (searchInput) searchInput.value = this.selectedModel;
        });

        // Searchable Dropdown
        const updateDropdown = (query = "") => {
            listDiv.innerHTML = '';
            const filtered = this.availableModels.filter(m => m.name.toLowerCase().includes(query.toLowerCase()));
            if (filtered.length === 0) {
                listDiv.innerHTML = `<div style="padding:8px; font-size:12px; color:#94a3b8;">No matches.</div>`;
            }
            filtered.forEach(m => {
                const item = document.createElement('div');
                item.className = 'gemini-dropdown-item';
                const tier = this._getModelTier(m.name);
                const badge = tier === "pro" ? "⚡" : tier.includes("flash") ? "🚀" : "•";
                item.innerHTML = `${badge} ${m.name}`;
                item.addEventListener('click', () => {
                    searchInput.value = m.name;
                    this.selectedModel = m.name;
                    localStorage.setItem("gemini_selected_model", m.name);
                    listDiv.classList.remove('show');
                    this._updateModelUsedBadge(m.name);
                });
                listDiv.appendChild(item);
            });
        };

        searchInput.addEventListener('focus', () => { listDiv.classList.add('show'); updateDropdown(searchInput.value); });
        searchInput.addEventListener('input', (e) => updateDropdown(e.target.value));

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !listDiv.contains(e.target)) listDiv.classList.remove('show');
            if (!panel.contains(e.target) && !btn.contains(e.target)) panel.classList.remove('show');
        });

        // Save Button
        document.getElementById('gemini-ui-save').addEventListener('click', async () => {
            const keyInput = document.getElementById('gemini-ui-key').value;
            if (!keyInput.includes('•') && keyInput !== this.apiKey) {
                if (keyInput.trim() === '') {
                    this.setApiKey('');
                    localStorage.removeItem(this.storageKey);
                } else {
                    this.setApiKey(keyInput);
                }
            }

            const typedModel = searchInput.value.trim();
            if (typedModel) {
                this.selectedModel = typedModel;
                localStorage.setItem("gemini_selected_model", typedModel);
            }

            const status = document.getElementById('gemini-status');
            status.innerHTML = "Connecting...";
            document.getElementById('gemini-key-indicator').style.background = '#eab308';

            try {
                const models = await this.discoverModels();
                this._populateDropdownUI(models);
                status.innerHTML = `<span style="color:#10b981">Connected! Found ${models.length} models.</span>`;
                document.getElementById('gemini-key-indicator').style.background = '#10b981';
                this._updateModelUsedBadge(this.selectedModel);
            } catch (err) {
                status.innerHTML = `<span style="color:#ef4444">${err.message}</span>`;
                document.getElementById('gemini-key-indicator').style.background = '#ef4444';
            }
        });

        // Initial UI state
        this._updateRateLimitUI();

        // Auto-fetch models on load
        this.discoverModels().then(models => this._populateDropdownUI(models)).catch(console.error);
    }

    _populateDropdownUI(models) {
        const searchInput = document.getElementById('gemini-search-input');
        const listDiv = document.getElementById('gemini-dropdown-list');
        if (!listDiv) return;

        listDiv.innerHTML = '';
        models.forEach(m => {
            const item = document.createElement('div');
            item.className = 'gemini-dropdown-item';
            const tier = this._getModelTier(m.name);
            const badge = tier === "pro" ? "⚡" : tier.includes("flash") ? "🚀" : "•";
            item.innerHTML = `${badge} ${m.name}`;
            item.addEventListener('click', () => {
                if (searchInput) searchInput.value = m.name;
                this.selectedModel = m.name;
                localStorage.setItem("gemini_selected_model", m.name);
                listDiv.classList.remove('show');
                this._updateModelUsedBadge(m.name);
            });
            listDiv.appendChild(item);
        });

        if (searchInput && this.selectedModel) searchInput.value = this.selectedModel;
        this._updateModelUsedBadge(this.selectedModel);
    }
}

// Global instance
window.gemini = new GeminiClient();
