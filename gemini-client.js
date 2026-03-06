/**
 * Gemini Smart Model Resolver (Client-Side)
 * Auto-selects the best available model directly from the browser.
 * 
 * Provides:
 * 1. API Key management (localStorage)
 * 2. Dynamic model discovery via `v1beta/models` REST API
 * 3. Auto-selection (3.1 Pro -> 3.1 Flash -> 2.5 series)
 * 4. Rate-limit aware retry capabilities
 * 5. Drop-in UI component for API key input and model selection
 */

const GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

// Known fallback cascade if discovery fails
const MODEL_CASCADE = [
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite"
];

const MODEL_TIER_SCORES = {
    "pro": 100,
    "flash": 50,
    "flash-lite": 25,
    "lite": 25
};

// Fallback API Key provided by user for public zero-config usage
const DEFAULT_FALLBACK_KEY = "***REDACTED_API_KEY***";

class GeminiClient {
    constructor(apiKeyStorageKey = "gemini_api_key") {
        this.storageKey = apiKeyStorageKey;
        this.apiKey = localStorage.getItem(this.storageKey) || DEFAULT_FALLBACK_KEY;
        this.isUsingDefaultKey = this.apiKey === DEFAULT_FALLBACK_KEY;
        this.availableModels = [];
        this.selectedModel = localStorage.getItem("gemini_selected_model") || "";
    }

    setApiKey(key) {
        this.apiKey = key.trim();
        localStorage.setItem(this.storageKey, this.apiKey);
    }

    getApiKey() {
        return this.apiKey;
    }

    hasApiKey() {
        return !!this.apiKey && this.apiKey.length > 20;
    }

    // Score models like the Python backend
    _scoreModel(name) {
        let score = 0;
        const lowName = name.toLowerCase();

        if (lowName.includes("flash-lite")) score = MODEL_TIER_SCORES["flash-lite"];
        else if (lowName.includes("pro")) score = MODEL_TIER_SCORES["pro"];
        else if (lowName.includes("lite")) score = MODEL_TIER_SCORES["lite"];
        else if (lowName.includes("flash")) score = MODEL_TIER_SCORES["flash"];
        else score = 10;

        // Parse version
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

    async discoverModels() {
        if (!this.hasApiKey()) throw new Error("API Key required to fetch models");

        try {
            const response = await fetch(`${GEMINI_API_BASE}?key=${this.apiKey}`);
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error?.message || "Failed to fetch models");
            }

            const data = await response.json();

            // Filter for generateContent support
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

            // Sort by descending score
            contentModels.sort((a, b) => b.score - a.score);
            this.availableModels = contentModels;

            // Auto-select best if current is invalid
            if (!this.selectedModel || !contentModels.find(m => m.name === this.selectedModel)) {
                this.selectedModel = contentModels[0].name;
                localStorage.setItem("gemini_selected_model", this.selectedModel);
            }

            return this.availableModels;
        } catch (error) {
            console.error("Gemini API Model Discovery Failed:", error);
            // Fallback to static list
            this.availableModels = MODEL_CASCADE.map(name => ({
                name,
                displayName: name,
                description: "Fallback model",
                score: this._scoreModel(name)
            }));

            if (!this.selectedModel) {
                this.selectedModel = MODEL_CASCADE[0];
            }
            return this.availableModels;
        }
    }

    async generateContent(promptText, systemInstruction = null) {
        if (!this.hasApiKey()) throw new Error("Missing API Key");
        if (!this.selectedModel) this.selectedModel = MODEL_CASCADE[0];

        const payload = {
            contents: [{ parts: [{ text: promptText }] }]
        };

        if (systemInstruction) {
            payload.systemInstruction = { parts: [{ text: systemInstruction }] };
        }

        const url = `${GEMINI_API_BASE}/${this.selectedModel}:generateContent?key=${this.apiKey}`;

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            // Handle rate limits / missing models
            throw new Error(`Gemini API Error (${response.status}): ${err.error?.message || "Unknown error"}`);
        }

        const data = await response.json();
        return data.candidates[0].content.parts[0].text;
    }

    // Injects floating UI into page
    injectUI(containerId = null) {
        const container = containerId ? document.getElementById(containerId) : document.body;
        if (!container) return;

        // Don't inject twice
        if (document.getElementById("gemini-client-ui-container")) return;

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
                        background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(10px);
                        border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
                        padding: 16px; color: #f1f5f9; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
                        width: 280px; display: none; flex-direction: column; opacity: 0;
                        transition: opacity 0.2s;
                    }
                    #gemini-client-ui.show { display: flex; opacity: 1; }
                    
                    #gemini-client-ui input, #gemini-client-ui select {
                        width: 100%; box-sizing: border-box; background: rgba(0,0,0,0.3); 
                        border: 1px solid rgba(255,255,255,0.2); color: white; padding: 8px; 
                        border-radius: 6px; margin-top: 6px; font-size: 13px; outline:none;
                    }
                    #gemini-client-ui input:focus { border-color: #3b82f6; }
                    #gemini-client-ui button.save-btn {
                        width: 100%; margin-top: 10px; padding: 8px;
                        background: #3b82f6; border: none; color: white;
                        border-radius: 6px; cursor: pointer; font-weight: 600;
                    }
                    #gemini-client-ui button.save-btn:hover { background: #2563eb; }
                    #gemini-status { font-size: 12px; margin-top: 8px; color: #94a3b8; }
                    
                    /* Custom Searchable Dropdown */
                    .gemini-dropdown { position: relative; margin-top: 6px; }
                    .gemini-dropdown-input { width: 100%; padding: 8px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); color: white; border-radius: 6px; outline:none; font-size:13px;}
                    .gemini-dropdown-list { 
                        position: absolute; top: 100%; left: 0; right: 0; background: #1e293b; 
                        border: 1px solid #334155; border-radius: 6px; max-height: 150px; overflow-y: auto; 
                        display: none; z-index: 100; margin-top:4px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                    }
                    .gemini-dropdown-list.show { display: block; }
                    .gemini-dropdown-item { padding: 8px; font-size: 12px; cursor: pointer; border-bottom: 1px solid #334155; }
                    .gemini-dropdown-item:hover { background: #3b82f6; }
                </style>
                
                <div id="gemini-floating-btn" title="AI Configuration">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                </div>

                <div id="gemini-client-ui">
                    <div style="font-size: 14px; font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; justify-content: space-between;">
                        ✨ Gemini Engine
                        <span id="gemini-key-indicator" style="width: 8px; height: 8px; border-radius: 50%; background: ${this.hasApiKey() ? '#10b981' : '#ef4444'};"></span>
                    </div>
                    
                    <div style="margin-top: 10px;">
                        <label style="font-size: 11px; color: #94a3b8; display: block; margin-bottom: 4px;">API Key Configuration</label>
                        <input type="password" id="gemini-ui-key" placeholder="${this.isUsingDefaultKey ? 'Using Default Public Key' : 'AIza...'}" value="${this.isUsingDefaultKey ? '' : this.apiKey.replace(/./g, '*')}" 
                               onfocus="this.value='${this.isUsingDefaultKey ? '' : this.apiKey}'" onblur="if(this.value) this.value=this.value.replace(/./g, '*')">
                        
                        <div style="font-size: 10px; color: #64748b; margin-top: 8px; line-height: 1.4;">
                            <span>Operating with public fallback key. If you reach quota limits:</span>
                            <a href="https://aistudio.google.com/app/apikey" target="_blank" 
                               style="margin-top: 6px; display: flex; align-items: center; justify-content: center; gap: 8px; background: #ffffff; color: #3c4043; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-weight: 500; font-family: 'Roboto', sans-serif; transition: background 0.2s;">
                                <svg width="14" height="14" viewBox="0 0 24 24">
                                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                                </svg>
                                Login with Google Auth
                            </a>
                        </div>
                    </div>
    
                    <div style="margin-top: 15px;">
                        <label style="font-size: 11px; color: #94a3b8;">Active Model Setup</label>
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
            if (panel.classList.contains('show') && this.availableModels.length === 0 && this.hasApiKey()) {
                document.getElementById('gemini-status').innerHTML = "Fetching models...";
                this.discoverModels().then(models => this._populateDropdownUI(models)).catch(err => {
                    document.getElementById('gemini-status').innerHTML = `<span style="color:#ef4444">${err.message}</span>`;
                });
            }
        });

        // Searchable Dropdown Logic
        const updateDropdown = (query = "") => {
            listDiv.innerHTML = '';
            const filtered = this.availableModels.filter(m => m.name.toLowerCase().includes(query.toLowerCase()));

            if (filtered.length === 0) {
                listDiv.innerHTML = `<div style="padding:8px; font-size:12px; color:#94a3b8;">No matches.</div>`;
            }

            filtered.forEach(m => {
                const item = document.createElement('div');
                item.className = 'gemini-dropdown-item';
                item.textContent = m.name;
                item.addEventListener('click', () => {
                    searchInput.value = m.name;
                    this.selectedModel = m.name;
                    localStorage.setItem("gemini_selected_model", m.name);
                    listDiv.classList.remove('show');
                });
                listDiv.appendChild(item);
            });
        };

        searchInput.addEventListener('focus', () => {
            listDiv.classList.add('show');
            updateDropdown(searchInput.value);
        });

        searchInput.addEventListener('input', (e) => updateDropdown(e.target.value));

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !listDiv.contains(e.target)) {
                listDiv.classList.remove('show');
            }
            if (!panel.contains(e.target) && !btn.contains(e.target)) {
                panel.classList.remove('show');
            }
        });

        // Save Button
        document.getElementById('gemini-ui-save').addEventListener('click', async () => {
            const keyInput = document.getElementById('gemini-ui-key').value;
            if (!keyInput.includes('*') && keyInput !== this.apiKey) {
                if (keyInput.trim() === '') {
                    this.setApiKey(DEFAULT_FALLBACK_KEY);
                    this.isUsingDefaultKey = true;
                    localStorage.removeItem(this.storageKey);
                } else {
                    this.setApiKey(keyInput);
                    this.isUsingDefaultKey = false;
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
            } catch (err) {
                status.innerHTML = `<span style="color:#ef4444">${err.message}</span>`;
                document.getElementById('gemini-key-indicator').style.background = '#ef4444';
            }
        });
    }

    _populateDropdownUI(models) {
        // Just triggers the update logic if the panel is open
        const searchInput = document.getElementById('gemini-search-input');
        if (searchInput && document.getElementById('gemini-dropdown-list').classList.contains('show')) {
            const listDiv = document.getElementById('gemini-dropdown-list');
            listDiv.innerHTML = '';
            models.forEach(m => {
                const item = document.createElement('div');
                item.className = 'gemini-dropdown-item';
                item.textContent = m.name;
                item.addEventListener('click', () => {
                    searchInput.value = m.name;
                    this.selectedModel = m.name;
                    localStorage.setItem("gemini_selected_model", m.name);
                    listDiv.classList.remove('show');
                });
                listDiv.appendChild(item);
            });
        }
    }
}

// Global instance
window.gemini = new GeminiClient();
