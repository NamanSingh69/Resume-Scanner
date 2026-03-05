# Resume Scanner (ATS) — Technical Report

## Architecture Overview

| Component | Technology |
|-----------|-----------|
| Language | Python 3.x |
| NLP | SpaCy, NLTK |
| OCR | Pytesseract, Pillow, pdf2image |
| ML | Scikit-learn (TF-IDF + Cosine Similarity) |
| AI | Google Generative AI (Gemini) |
| Text Analysis | python-textstat |

### Pipeline
```
[Resume PDF] → [OCR (Pytesseract)] → [Text Extraction]
                                           ↓
                              [SpaCy NER + NLTK Tokenization]
                                           ↓
[Job Description] → [TF-IDF Vectorization] → [Cosine Similarity Score]
                                           ↓
                              [Gemini AI Analysis] → [ATS Report]
```

## Study Findings

- **Core Function**: ATS-style resume analysis against job descriptions
- **NLP Pipeline**: SpaCy NER for entity extraction + NLTK for tokenization and stopwords
- **Matching**: TF-IDF vectorization with cosine similarity scoring
- **AI Enhancement**: Gemini API provides qualitative feedback and improvement suggestions
- **Heavy Dependencies**: SpaCy English model (`en_core_web_sm` ~50MB), Tesseract OCR, poppler
- **Deployment Verdict**: ❌ **Not deployable on free tier** — CLI tool, requires system deps (Tesseract, Poppler), SpaCy model download, total memory footprint ~300MB+

## Local Setup Guide

```bash
# 1. Install system dependencies
# Windows: Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
# Windows: Install Poppler from https://github.com/oschwartz10612/poppler-windows/releases
# macOS:   brew install tesseract poppler
# Linux:   apt install tesseract-ocr poppler-utils

# 2. Navigate to project
cd "Resume Scanner"

# 3. Setup Python environment
python -m venv venv
venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

# 5. Set API key
# Create .env file:
# GOOGLE_API_KEY=your_key_here

# 6. Run
python main.py
```

## 🔑 Getting Your Free Gemini API Key

1. Visit **[Google AI Studio](https://aistudio.google.com/app/apikey)**
2. Sign in with your Google account — **completely free**
3. Click **"Create API Key"** → Copy the key
4. Add to `.env`: `GOOGLE_API_KEY=your_key_here`

### Model Fallback
The app uses Gemini for qualitative analysis. If the primary model is rate-limited, consider configuring fallback:
```python
MODEL_CASCADE = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-flash-latest"]
```
