import os
import json
import tempfile
import logging
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import google.generativeai as genai
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
from gemini_model_resolver import get_best_model, get_best_model_name

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Vercel handles the 4.5MB limit, but we enforce 4.5MB locally just in case.
app.config['MAX_CONTENT_LENGTH'] = 4.5 * 1024 * 1024  
app.secret_key = os.urandom(24)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'txt', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Read local index.html if it exists, for local development
HTML_TEMPLATE = ""
template_path = os.path.join(os.path.dirname(__file__), "index.html")
if os.path.exists(template_path):
    with open(template_path, 'r', encoding='utf-8') as f:
        HTML_TEMPLATE = f.read()

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE) if HTML_TEMPLATE else "index.html not found, but API is running."

@app.route('/api/analyze', methods=['POST'])
@app.route('/analyze', methods=['POST'])
def analyze():
    """Analyze a resume against a job description using Gemini File API or client-side text fallback."""
    try:
        job_description = request.form.get('job_description', '').strip()
        if not job_description:
            job_description = "General Resume Analysis: Evaluate this resume for general professional strengths, weaknesses, and overall ATS readiness without a specific role in mind."

        # Optional: Extracted text from client (fallback if file > 4.5MB)
        client_extracted_text = request.form.get('resume_text', '')
        
        file = request.files.get('resume')
        tmp_path = None

        if not file and not client_extracted_text:
            return jsonify({"error": "Valid resume file or extracted text required"}), 400
        
        if file and not allowed_file(file.filename):
             return jsonify({"error": "Valid resume file required (PDF, PNG, JPG, TXT, DOCX)"}), 400

        # Configure Gemini
        google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("VITE_GEMINI_API_KEY")
        if not google_api_key:
            return jsonify({"error": "Server configuration error: Gemini API key missing"}), 500
        
        genai.configure(api_key=google_api_key)
        
        # System instructions
        system_instruction = """
        You are an expert ATS (Applicant Tracking System) and senior technical recruiter. 
        Analyze the provided resume against the job description.
        Return ONLY a raw JSON object with this exact structure, do not include markdown blocks:
        {
          "ats_score": number (0-100 overall match score),
          "component_scores": { "Skills Match": number, "Experience": number, "Formatting": number },
          "ai_feedback": ["Specific actionable point 1", "Point 2", "Point 3"],
          "matched_keywords": ["keyword1", "keyword2"],
          "missing_keywords": ["keyword1", "keyword2"]
        }
        """
        user_prompt = f"JOB DESCRIPTION:\n{job_description}\n\n"
        
        # Use gemini_model_resolver to get the best model, preferring 'pro'
        # If 'pro' fails or is rate-limited, it automatically falls back!
        try:
            model = get_best_model(google_api_key, preferred_tier="pro")
            model_name_used = get_best_model_name(google_api_key, preferred_tier="pro")
            logger.info(f"Selected model for analysis: {model_name_used}")
        except Exception as e:
            logger.warning(f"Resolver failed, using hardcoded fallback: {e}")
            model = genai.GenerativeModel("gemini-2.5-flash")
        
        contents = []

        if file:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name

            try:
                # Upload the file to Gemini via File API
                gemini_file = genai.upload_file(path=tmp_path, display_name=secure_filename(file.filename))
                contents.append(gemini_file)
                contents.append(user_prompt)
            except Exception as e:
                logger.error(f"Gemini File API upload failed: {e}")
                # Clean up and abort
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return jsonify({"error": f"Failed to upload file to Gemini: {str(e)}"}), 500
        else:
            # Fallback text mode
            user_prompt += f"RESUME TEXT:\n{client_extracted_text}"
            contents.append(user_prompt)

        try:
            response = model.generate_content(
                contents,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                ),
                system_instruction=system_instruction
            )
            
            # Delete file from Gemini if it was uploaded
            if file:
                try:
                    genai.delete_file(gemini_file.name)
                except Exception as e:
                    logger.warning(f"Failed to delete file from Gemini API: {e}")
                    
            return response.text, 200, {'Content-Type': 'application/json'}
            
        finally:
            # Cleanup local temp file
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/health')
@app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "resume-ats-scanner"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
