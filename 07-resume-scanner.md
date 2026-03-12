# Resume Scanner — Complete Standalone Agent Prompt

## Project Identity

| Field | Value |
|-------|-------|
| **Project Folder** | `C:\Users\namsi\Desktop\Projects\Resume Scanner` |
| **Tech Stack** | Python backend + Vanilla JS frontend |
| **Vercel URL** | https://resume-scanner-ats.vercel.app/ |
| **GitHub Repo** | `NamanSingh69/Resume-Scanner` (already exists) |
| **Vercel Env Vars** | `GEMINI_API_KEY` is set |

### Key Files
- `app.py` — Python backend with resume scanning logic
- `index.html` or `templates/index.html` — Main HTML page (Dark Mode UI)
- `static/gemini-client.js` — Updated to v2 (28KB) in a previous session (verify it's still 28KB)
- `static/` — CSS, JS, static assets
- `ux-manager.js` — Shared UX component system (Skeleton loaders, ToastManager, EmptyState) — may or may not be present
- `api/` — Vercel Serverless Functions
- `vercel.json` — Route configuration
- `requirements.txt` — Python dependencies

### Previous Work History
- `gemini-client.js` was updated from v1 (12KB) to v2 (28KB) in a Gemini Feature Rollout session
- A React hydration bug (`??>""`) was fixed in a previous session (rendering broken HTML in DOM)
- UX components (Skeletons, Toasts, Empty States) were added in a UX Mandate rollout session

---

## Shared Infrastructure Context (CRITICAL)

### Design System — "UX Mandate"
4 states: Loading (skeletons), Success (toasts), Empty (beautiful null), Error (actionable recovery). Never `alert()`.

### Gemini Client (Python/Vanilla JS)
`gemini-client.js` v2 (28KB): Pro/Fast toggle, rate limit counter, model cascade.
### Smart Model Cascade (March 2026)
**Primary (Free Preview):** `gemini-3.1-pro-preview` → `gemini-3-flash-preview` → `gemini-3.1-flash-lite-preview`
**Fallback (Free Stable):** `gemini-2.5-pro` → `gemini-2.5-flash` → `gemini-2.5-flash-lite`
**Note:** `gemini-2.0-*` deprecated March 3, 2026. Do NOT use.
- Config: `window.GEMINI_CONFIG = { needsRealTimeData: false }`
- Pro = first model in cascade, Fast = second model

### UX Manager (`ux-manager.js` + `Skeleton.css`)
A shared component system that provides:
- `window.uxManager.showSkeleton(targetElement)` — inject animated skeleton into target
- `window.uxManager.showToast(message, type)` — show toast (success/error/info)
- `window.uxManager.showEmptyState(targetElement, message)` — show beautiful null state
If this file doesn't exist in the project, the functionality should be implemented inline.

### Security: `os.environ.get("GEMINI_API_KEY")`, never hardcode
### Mobile: 375px–1920px, touch targets ≥ 44px, no horizontal scroll

---

## Current Live State (Verified March 10, 2026)

| Feature | Status | Details |
|---------|--------|---------|
| Site loads | ✅ 200 OK | Minimalist ATS scanner with Dark Mode UI |
| Login wall | ✅ None | |
| Pro/Fast Toggle | ❌ NOT VISIBLE | Despite gemini-client.js v2 being installed, the toggle is not rendering |
| Rate Limit Counter | ❌ NOT VISIBLE | Same issue |
| Empty State | ✅ Present | Dark Mode UI with "Drop Resume" upload area |
| Skeleton Loaders | ❌ NOT VERIFIED | Cannot trigger — "Analyze Resume" button fails/disabled |
| Toasts | ⚠️ Partial | Some toast-like notifications may exist |
| Mobile Responsive | ✅ Yes | Layout adapts at 375px |
| **Critical Bug** | ❌ "Analyze Resume" broken | Button remains disabled or fails silently even after populating Job Description and uploading a resume |
| **Rendering Bug** | ⚠️ Check for `??>""` | A hydration bug was fixed before but may have regressed |

---

## Required Changes

### 1. Fix "Analyze Resume" Button (CRITICAL — Primary Objective)
The core functionality is broken — the button either stays disabled or fails silently.

**Debugging steps:**
1. Inspect the "Analyze Resume" button in DevTools → check if it has a `disabled` attribute
2. Find the click handler: `grep -r "Analyze\|analyze\|scan\|submit" *.js *.html`
3. Common causes:
   - Form validation is too strict (requiring fields that aren't visible)
   - The button's `disabled` state depends on conditions that never resolve
   - The API endpoint it calls doesn't exist or returns an error
4. **Fix the validation logic** so the button enables correctly when:
   - Job Description text area has content
   - A resume file (PDF/DOCX) is uploaded
5. **Fix the API call** — ensure the button triggers a POST to the correct endpoint
6. After the API call succeeds, display the ATS match score and feedback

### 2. Fix gemini-client.js v2 Integration
The file was updated to v2 (28KB) previously but the toggle/counter aren't showing:
- Verify the file is included in the HTML: `<script src="/static/gemini-client.js"></script>`
- Verify `window.GEMINI_CONFIG = { needsRealTimeData: false }` is set before the script loads
- Check for JavaScript errors that prevent the script from initializing
- After fixing, the ⚡ PRO / 🚀 FAST toggle and rate limit badge should auto-inject

### 3. Check for Hydration Bug Regression
- Search the rendered HTML for `??>""` or `??\"` strings
- If found, fix the templating issue in the HTML (likely a Jinja2 template with a broken conditional: `{{ variable ?? "default" }}` — Python/Jinja2 doesn't support `??` operator)
- Replace with `{{ variable or "default" }}` or `{{ variable if variable else "default" }}`

### 4. Add/Verify Toast Notifications
- Replace any remaining `alert()` calls with toast notifications
- Success toast: "Resume analysis complete! ATS Score: X%"
- Error toast: "Failed to analyze resume. Please try again."

### 5. Mobile Responsiveness
- Resume upload drag-drop zone must work on touch devices (file input fallback)
- Job Description textarea must be full-width on mobile
- ATS score result card must not overflow
- All text must be readable at 375px

### 6. GitHub & Deployment
- Push to `Resume-Scanner` repo
- `git add -A && git commit -m "fix: analyze button, gemini client v2 integration, hydration bug, mobile" && git push`
- Redeploy: `npx vercel --prod --yes`
- Verify at https://resume-scanner-ats.vercel.app/

---

## Verification Checklist
1. ✅ Site loads — no `??>""` rendering bug visible
2. ✅ Pro/Fast toggle visible (floating button)
3. ✅ Rate limit counter visible
4. ✅ Paste a job description + upload a resume → "Analyze Resume" button is enabled
5. ✅ Click Analyze → skeleton loader appears → results display with success toast
6. ✅ ATS score and feedback are shown correctly
7. ✅ Resize to 375px → fully usable, upload works on touch
8. ✅ DevTools console → zero errors
9. ✅ `gemini-client.js` is 28KB+ (v2)
