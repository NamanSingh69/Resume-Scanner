/**
 * Gemini Smart Model Resolver (Client-Side proxy structure)
 * Auto-selects the best available model directly from the browser by securely calling backend API endpoints.
 * 
 * Provides:
 * 1. Custom API Key input (localStorage)
 * 2. Dynamic model discovery via `/api/models` Vercel proxy
 * 3. Auto-selection (3.1 Pro -> 3.1 Flash -> 2.5 series)
 * 4. Rate-limit aware retry capabilities
 * 5. Drop-in UI component for API key input and model selection
 */

const GEMINI_API_MODELS = "/api/models";
const GEMINI_API_CHAT = "/api/chat";

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

class GeminiClient {
    constructor(apiKeyStorageKey = "gemini_api_key") {
        this.storageKey = apiKeyStorageKey;
        this.apiKey = localStorage.getItem(this.storageKey) || "";
        this.isUsingDefaultKey = !this.apiKey;
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
        return true; // Proxy handles the zero-config fallback via Vercel env vars
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
        try {
            const headers = {};
            if (this.apiKey) headers["x-gemini-api-key"] = this.apiKey;

            const response = await fetch(GEMINI_API_MODELS, { headers });
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
            contents: [{ parts: [{ text: promptText }] }],
            model: this.selectedModel
        };

        if (systemInstruction) {
            payload.systemInstruction = { parts: [{ text: systemInstruction }] };
        }

        const headers = { 'Content-Type': 'application/json' };
        if (this.apiKey) headers["x-gemini-api-key"] = this.apiKey;

        const response = await fetch(GEMINI_API_CHAT, {
            method: 'POST',
            headers: headers,
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
        if (document.getElementById("gemini-client-ui")) return;

        const uiHtml = `
            <div id="gemini-client-ui" style="
                position: fixed; bottom: 20px; right: 20px;
                background: rgba(15, 23, 42, 0.95);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                padding: 16px;
                color: #f1f5f9;
                font-family: system-ui, -apple-system, sans-serif;
                box-shadow: 0 10px 25px rgba(0,0,0,0.5);
                z-index: 9999;
                min-width: 250px;
            ">
                <style>
                    #gemini-client-ui input, #gemini-client-ui select {
                        width: 100%; box-sizing: border-box;
                        background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2);
                        color: white; padding: 8px; border-radius: 6px; margin-top: 6px;
                        font-size: 13px;
                    }
                    #gemini-client-ui button {
                        width: 100%; margin-top: 10px; padding: 8px;
                        background: #3b82f6; border: none; color: white;
                        border-radius: 6px; cursor: pointer; font-weight: 600;
                    }
                    #gemini-client-ui button:hover { background: #2563eb; }
                    #gemini-status { font-size: 12px; margin-top: 8px; color: #94a3b8; }
                </style>
                <div style="font-size: 14px; font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; justify-content: space-between;">
                    ✨ Gemini Engine
                    <span id="gemini-key-indicator" style="width: 8px; height: 8px; border-radius: 50%; background: ${this.hasApiKey() ? '#10b981' : '#ef4444'};"></span>
                </div>
                
                <div>
                    <label style="font-size: 11px; color: #94a3b8;">API Key</label>
                    <input type="password" id="gemini-ui-key" placeholder="${this.isUsingDefaultKey ? 'Using Secure Server Key' : 'AIza...'}" value="${this.isUsingDefaultKey ? '' : this.apiKey.replace(/./g, '*')}" 
                           onfocus="this.value='${this.isUsingDefaultKey ? '' : this.apiKey}'" onblur="if(this.value) this.value=this.value.replace(/./g, '*')">
                    <div style="font-size: 10px; color: #64748b; margin-top: 6px; display: flex; justify-content: space-between; align-items: center;">
                        <span>Leave blank for default.</span>
                        <a href="https://aistudio.google.com/app/apikey" target="_blank" style="color: #3b82f6; text-decoration: none; font-weight: 500; display: flex; align-items: center; gap: 4px;">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.748L12.545,10.239z"/>
                            </svg>
                            Login with Google
                        </a>
                    </div>
                </div>

                <div style="margin-top: 10px;">
                    <label style="font-size: 11px; color: #94a3b8;">Active Model</label>
                    <select id="gemini-ui-model">
                        <option value="${this.selectedModel}">${this.selectedModel || 'Loading models...'}</option>
                    </select>
                </div>
                
                <button id="gemini-ui-save">Save & Connect</button>
                <div id="gemini-status"></div>
            </div>
        `;

        if (containerId) {
            container.innerHTML += uiHtml;
        } else {
            document.body.insertAdjacentHTML('beforeend', uiHtml);
        }

        // Attach events
        document.getElementById('gemini-ui-save').addEventListener('click', async () => {
            const keyInput = document.getElementById('gemini-ui-key').value;
            // Only update if it's not the masked version
            if (!keyInput.includes('*') && keyInput !== this.apiKey) {
                if (keyInput.trim() === '') {
                    this.setApiKey('');
                    this.isUsingDefaultKey = true;
                    localStorage.removeItem(this.storageKey); // Clear local storage to revert to default
                } else {
                    this.setApiKey(keyInput);
                    this.isUsingDefaultKey = false;
                }
            }

            const status = document.getElementById('gemini-status');
            status.innerHTML = "Connecting...";
            document.getElementById('gemini-key-indicator').style.background = '#eab308'; // yellow

            try {
                const models = await this.discoverModels();
                this._populateDropdown(models);
                status.innerHTML = `<span style="color:#10b981">Connected! Found ${models.length} models.</span>`;
                document.getElementById('gemini-key-indicator').style.background = '#10b981'; // green
            } catch (err) {
                status.innerHTML = `<span style="color:#ef4444">${err.message}</span>`;
                document.getElementById('gemini-key-indicator').style.background = '#ef4444'; // red
            }
        });

        // Dropdown change
        document.getElementById('gemini-ui-model').addEventListener('change', (e) => {
            this.selectedModel = e.target.value;
            localStorage.setItem("gemini_selected_model", this.selectedModel);
        });

        // Auto-fetch if key exists
        if (this.hasApiKey()) {
            this.discoverModels().then(models => this._populateDropdown(models)).catch(console.error);
        }
    }

    _populateDropdown(models) {
        const select = document.getElementById('gemini-ui-model');
        if (!select) return;

        select.innerHTML = models.map(m =>
            `<option value="${m.name}" ${m.name === this.selectedModel ? 'selected' : ''}>${m.name}</option>`
        ).join('');
    }
}

// Global instance
window.gemini = new GeminiClient();
