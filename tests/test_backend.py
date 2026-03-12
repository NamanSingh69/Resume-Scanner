import os
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from api.index import app
from io import BytesIO

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_check(client):
    """Test the health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {"status": "ok", "service": "resume-ats-scanner"}

def test_analyze_no_data(client):
    """Test analyze endpoint with missing data"""
    response = client.post('/api/analyze')
    assert response.status_code == 400
    assert "Valid resume file or extracted text required" in response.json['error']

def test_analyze_missing_file(client):
    """Test analyze endpoint with missing file and extracted text"""
    response = client.post('/api/analyze', data={"job_description": "Looking for software engineer"})
    assert response.status_code == 400
    assert "Valid resume file or extracted text required" in response.json['error']

def test_analyze_text_fallback(client, monkeypatch):
    """Test analyze endpoint with text fallback to bypass file limit logic"""
    # Mocking genai to avoid actual API calls in tests
    class MockResponse:
        @property
        def text(self):
            return json.dumps({
                "ats_score": 85,
                "component_scores": {"Skills Match": 90, "Experience": 80, "Formatting": 100},
                "ai_feedback": ["Good resume"],
                "matched_keywords": ["python"],
                "missing_keywords": ["java"]
            })
            
    class MockModel:
        def generate_content(self, *args, **kwargs):
            return MockResponse()
            
    monkeypatch.setattr("google.generativeai.GenerativeModel", lambda model_name: MockModel())
    # We must mock configure since the API key might not be there
    monkeypatch.setattr("google.generativeai.configure", lambda *args, **kwargs: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test_key")
    
    response = client.post('/api/analyze', data={
        "job_description": "Looking for Python developer",
        "resume_text": "I am a Python developer with 5 years experience."
    })
    
    assert response.status_code == 200
    data = response.json
    assert data["ats_score"] == 85
    assert "python" in data["matched_keywords"]
