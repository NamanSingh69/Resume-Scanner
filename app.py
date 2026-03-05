"""
Resume Scanner ATS — Web Interface
Flask web wrapper for the Resume ATS CLI tool.
Provides file upload, job description input, and visual ATS scoring.
"""
import os
import sys
import json
import tempfile
import logging
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max
app.secret_key = os.urandom(24)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ─── HTML Template ───────────────────────────────────────────────────────────
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Resume ATS Scanner</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0a0a0f;
            --surface: #12121a;
            --surface-2: #1a1a2e;
            --accent: #6c63ff;
            --accent-glow: rgba(108, 99, 255, 0.15);
            --text: #e8e8f0;
            --text-muted: #8888a0;
            --success: #00d68f;
            --warning: #ffaa00;
            --danger: #ff4d6a;
            --border: rgba(255,255,255,0.06);
            --radius: 16px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: #0a0a0f url('/static/bg.png') no-repeat center center fixed;
            background-size: cover;
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            margin: 0;
        }
        /* Mobile-friendly container */
        .container {
            width: 100%;
            max-width: 720px;
            backdrop-filter: blur(8px);
            background: rgba(0,0,0,0.3);
            border-radius: 24px;
            padding: 2rem;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .container {
            width: 100%;
            max-width: 720px;
        }
        h1 {
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent), #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.25rem;
        }
        .subtitle {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 2rem;
        }
        .card {
            background: rgba(18, 18, 26, 0.65);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: var(--radius);
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        label {
            display: block;
            font-weight: 500;
            margin-bottom: 0.5rem;
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        textarea {
            width: 100%;
            min-height: 120px;
            background: rgba(26, 26, 46, 0.5);
            backdrop-filter: blur(4px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 1rem;
            color: var(--text);
            font-family: inherit;
            font-size: 0.9rem;
            resize: vertical;
            transition: all 0.3s ease;
        }
        textarea:focus {
            outline: none;
            border-color: var(--accent);
            background: rgba(26, 26, 46, 0.8);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }
        .drop-zone {
            border: 2px dashed rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            background: rgba(26, 26, 46, 0.5);
            backdrop-filter: blur(4px);
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: var(--accent);
            background: rgba(108, 99, 255, 0.1);
            transform: translateY(-2px);
        }
        .drop-zone input { display: none; }
        .drop-zone .icon { font-size: 2rem; margin-bottom: 0.5rem; }
        .drop-zone .hint { color: var(--text-muted); font-size: 0.85rem; }
        .file-name { color: var(--accent); font-weight: 500; margin-top: 0.5rem; }
        button {
            width: 100%;
            padding: 1rem;
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            border: none;
            border-radius: 12px;
            color: white;
            font-family: inherit;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.2s;
        }
        button:hover { transform: translateY(-1px); box-shadow: 0 8px 30px var(--accent-glow); }
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        
        /* Results */
        .results { display: none; }
        .results.show { display: block; }
        .score-ring {
            width: 140px; height: 140px;
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 1.5rem;
            font-size: 2.5rem; font-weight: 700;
            position: relative;
        }
        .score-ring::before {
            content: '';
            position: absolute; inset: 0;
            border-radius: 50%;
            padding: 4px;
            background: conic-gradient(var(--score-color) calc(var(--score) * 3.6deg), var(--surface-2) 0);
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }
        .metric {
            background: var(--surface-2);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }
        .metric .value {
            font-size: 1.5rem;
            font-weight: 700;
        }
        .metric .label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0.25rem;
        }
        .section-title {
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin: 1.5rem 0 0.75rem;
        }
        .feedback-item {
            background: var(--surface-2);
            border-radius: 10px;
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            line-height: 1.5;
        }
        .loading {
            display: none;
            text-align: center;
            padding: 2rem;
        }
        .loading.show { display: block; }
        .spinner {
            width: 40px; height: 40px;
            border: 3px solid var(--surface-2);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 1rem;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .error { color: var(--danger); padding: 1rem; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 Resume ATS Scanner</h1>
        <p class="subtitle">AI-powered resume analysis against job descriptions</p>

        <form id="ats-form">
            <div class="card">
                <label for="job-desc">Job Description</label>
                <textarea id="job-desc" placeholder="Paste the job description here..." required></textarea>
            </div>

            <div class="card">
                <label>Resume Upload</label>
                <div class="drop-zone" id="drop-zone">
                    <input type="file" id="resume-file" accept=".pdf,.png,.jpg,.jpeg,.txt">
                    <div class="icon">📎</div>
                    <div>Drop resume here or <strong>click to browse</strong></div>
                    <div class="hint">PDF, PNG, JPG, or TXT (max 10MB)</div>
                    <div class="file-name" id="file-name"></div>
                </div>
            </div>

            <button type="submit" id="submit-btn">🔍 Analyze Resume</button>
        </form>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <div>Analyzing your resume with AI...</div>
        </div>

        <div class="results" id="results">
            <div class="card">
                <div class="score-ring" id="score-ring">
                    <span id="score-text">—</span>
                </div>
                <div class="metric-grid" id="metrics"></div>
            </div>
            <div class="card">
                <div class="section-title">AI Feedback</div>
                <div id="feedback"></div>
            </div>
            <div class="card">
                <div class="section-title">Keywords Found</div>
                <div id="keywords" style="font-size:0.9rem; line-height:1.8;"></div>
            </div>
        </div>
    </div>

    <script>
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('resume-file');
        const fileNameEl = document.getElementById('file-name');

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                fileNameEl.textContent = e.dataTransfer.files[0].name;
            }
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) fileNameEl.textContent = fileInput.files[0].name;
        });

        document.getElementById('ats-form').addEventListener('submit', async e => {
            e.preventDefault();
            const jobDesc = document.getElementById('job-desc').value;
            const file = fileInput.files[0];
            if (!file) { alert('Please upload a resume'); return; }

            const btn = document.getElementById('submit-btn');
            btn.disabled = true;
            document.getElementById('loading').classList.add('show');
            document.getElementById('results').classList.remove('show');

            const formData = new FormData();
            formData.append('resume', file);
            formData.append('job_description', jobDesc);

            try {
                const res = await fetch('/api/analyze', { method: 'POST', body: formData });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Analysis failed');
                renderResults(data);
            } catch (err) {
                document.getElementById('results').innerHTML = `<div class="card error">${err.message}</div>`;
                document.getElementById('results').classList.add('show');
            } finally {
                btn.disabled = false;
                document.getElementById('loading').classList.remove('show');
            }
        });

        function renderResults(data) {
            const score = Math.round(data.ats_score || 0);
            const color = score >= 70 ? 'var(--success)' : score >= 40 ? 'var(--warning)' : 'var(--danger)';
            
            const ring = document.getElementById('score-ring');
            ring.style.setProperty('--score', score);
            ring.style.setProperty('--score-color', color);
            document.getElementById('score-text').textContent = score;
            document.getElementById('score-text').style.color = color;

            const metrics = document.getElementById('metrics');
            metrics.innerHTML = Object.entries(data.component_scores || {}).map(([k, v]) =>
                `<div class="metric"><div class="value" style="color:${v >= 60 ? 'var(--success)' : 'var(--warning)'}">${Math.round(v)}%</div><div class="label">${k}</div></div>`
            ).join('');

            const feedback = document.getElementById('feedback');
            const items = data.ai_feedback || data.suggestions || ['No AI feedback available'];
            feedback.innerHTML = (Array.isArray(items) ? items : [items]).map(f =>
                `<div class="feedback-item">${f}</div>`
            ).join('');

            const keywords = document.getElementById('keywords');
            const matched = data.matched_keywords || [];
            const missing = data.missing_keywords || [];
            keywords.innerHTML = 
                matched.map(k => `<span style="background:rgba(0,214,143,0.15);color:var(--success);padding:4px 10px;border-radius:6px;margin:3px;display:inline-block;">✓ ${k}</span>`).join('') +
                missing.map(k => `<span style="background:rgba(255,77,106,0.15);color:var(--danger);padding:4px 10px;border-radius:6px;margin:3px;display:inline-block;">✗ ${k}</span>`).join('');

            document.getElementById('results').classList.add('show');
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Analyze a resume against a job description."""
    try:
        job_description = request.form.get('job_description', '')
        if not job_description:
            return jsonify({"error": "Job description is required"}), 400

        file = request.files.get('resume')
        if not file or not allowed_file(file.filename):
            return jsonify({"error": "Valid resume file required (PDF, PNG, JPG, TXT)"}), 400

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        try:
            # Import the ATS engine
            from main import ResumeATS
            
            ats = ResumeATS(job_description)
            resume_text = ats.extract_text(tmp_path)
            
            if not resume_text.strip():
                return jsonify({"error": "Could not extract text from resume"}), 400

            # Run full analysis
            parsed = ats.parse_resume(resume_text)
            score_result = ats.calculate_ats_score(resume_text)
            keyword_analysis = ats.analyze_keywords(resume_text)
            
            # Get AI feedback if available
            ai_feedback = []
            if ats.gemini_available:
                try:
                    ai_result = ats.get_ai_suggestions(resume_text)
                    if isinstance(ai_result, str):
                        ai_feedback = [line.strip() for line in ai_result.split('\n') if line.strip()]
                    elif isinstance(ai_result, list):
                        ai_feedback = ai_result
                except Exception as e:
                    logger.warning(f"AI feedback failed: {e}")
                    ai_feedback = ["AI feedback unavailable — analysis based on NLP scoring only."]

            response = {
                "ats_score": score_result.get("overall_score", 0) if isinstance(score_result, dict) else 0,
                "component_scores": score_result.get("component_scores", {}) if isinstance(score_result, dict) else {},
                "matched_keywords": keyword_analysis.get("matched", []) if isinstance(keyword_analysis, dict) else [],
                "missing_keywords": keyword_analysis.get("missing", []) if isinstance(keyword_analysis, dict) else [],
                "ai_feedback": ai_feedback,
                "sections_found": list(parsed.keys()) if isinstance(parsed, dict) else [],
            }
            return jsonify(response)
            
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "resume-ats-scanner"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
