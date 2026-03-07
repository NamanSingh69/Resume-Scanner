import json
import re
import os
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Tuple, Optional
import google.generativeai as genai
import textstat
import logging
import argparse
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("ResumeATS")

# Download necessary resources (only need to do this once)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    logger.info("Downloading NLTK punkt tokenizer...")
    nltk.download('punkt', quiet=True)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    logger.info("Downloading NLTK stopwords...")
    nltk.download('stopwords', quiet=True)
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    logger.info("Downloading NLTK WordNet...")
    nltk.download('wordnet', quiet=True)

# Load SpaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.info("Downloading en_core_web_sm model...")
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# Initialize lemmatizer
lemmatizer = WordNetLemmatizer()

class ResumeATS:
    def __init__(self, job_description: str):
        """
        Initialize the ResumeATS with a job description.
        
        Args:
            job_description: The text of the job description to compare against
        """
        self.job_description = job_description
        self.job_keywords = self.extract_keywords(job_description)
        
        # Configure weights for ATS score calculation
        self.weights = {
            'skills': 0.4,
            'experience': 0.3,
            'keywords': 0.15,
            'education': 0.1,
            'readability': 0.05
        }
        
        # Industry-specific keywords database
        self.industry_keywords = {
            'data_science': [
                'machine learning', 'data analysis', 'python', 'r', 'sql', 'tensorflow',
                'pytorch', 'pandas', 'numpy', 'tableau', 'power bi', 'statistics',
                'deep learning', 'nlp', 'natural language processing', 'computer vision', 
                'big data', 'hadoop', 'spark', 'data visualization', 'data mining', 
                'predictive modeling', 'ai', 'artificial intelligence', 'data engineering'
            ],
            'software_dev': [
                'java', 'javascript', 'python', 'c++', 'c#', 'react', 'angular', 'vue', 'node.js',
                'aws', 'azure', 'google cloud', 'devops', 'ci/cd', 'git', 'docker', 'kubernetes', 
                'microservices', 'rest api', 'graphql', 'agile', 'scrum', 'database', 'sql', 
                'nosql', 'full stack', 'front end', 'back end', 'web development', 'mobile development'
            ],
            'marketing': [
                'seo', 'sem', 'social media marketing', 'content marketing', 'email marketing',
                'digital marketing', 'analytics', 'google ads', 'facebook ads', 'branding', 
                'market research', 'customer acquisition', 'crm', 'hubspot', 'salesforce', 
                'marketing automation', 'public relations', 'brand strategy', 'market analysis'
            ],
            'finance': [
                'financial analysis', 'accounting', 'budgeting', 'forecasting', 'investment',
                'risk management', 'financial reporting', 'excel', 'bloomberg', 'cfa',
                'portfolio management', 'valuation', 'merger', 'acquisition', 'financial modeling'
            ],
            'healthcare': [
                'patient care', 'clinical', 'medical', 'healthcare', 'hospital', 'treatment',
                'diagnosis', 'pharmaceutical', 'therapy', 'nursing', 'medicine', 'doctor',
                'physician', 'emr', 'electronic medical records', 'hipaa'
            ]
        }
        
        # Attempt to initialize Gemini API with dynamic model discovery
        # Get your free API key at: https://aistudio.google.com/app/apikey
        self.gemini_available = False
        self._model_cascade = [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-flash-latest",
        ]
        google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("VITE_GEMINI_API_KEY") or "***REDACTED_API_KEY***"
        if google_api_key:
            genai.configure(api_key=google_api_key)
            
            # Try dynamic model discovery first
            try:
                from gemini_model_resolver import get_best_model
                self.gemini_model = get_best_model(preferred_tier="pro")
                self.gemini_available = True
                logger.info(f"Dynamic model discovery selected: {self.gemini_model.model_name}")
            except ImportError:
                logger.info("gemini_model_resolver not found, using static cascade")
                self._init_static_cascade()
            except Exception as e:
                logger.warning(f"Dynamic discovery failed: {e}. Using static cascade.")
                self._init_static_cascade()
        else:
            logger.warning(
                "GOOGLE_API_KEY not set. Get a free key at: "
                "https://aistudio.google.com/app/apikey"
            )
    
    def _init_static_cascade(self):
        """Fallback: try models from the static cascade list."""
        for model_name in self._model_cascade:
            try:
                self.gemini_model = genai.GenerativeModel(model_name)
                self.gemini_model.count_tokens("test")
                self.gemini_available = True
                logger.info(f"Gemini API initialized with model: {model_name}")
                return
            except Exception as e:
                logger.warning(f"Model {model_name} unavailable: {e}. Trying next...")
        if not self.gemini_available:
            self.gemini_model = genai.GenerativeModel(self._model_cascade[-1])
            self.gemini_available = True
            logger.warning(f"Using fallback model: {self._model_cascade[-1]}")

    def extract_text(self, file_path: str) -> str:
        """
        Extracts text from PDF or image files.
        
        Args:
            file_path: Path to the resume file (PDF, JPG, PNG)
            
        Returns:
            Extracted text from the file
            
        Raises:
            ValueError: If the file format is unsupported or extraction fails
        """
        logger.info(f"Extracting text from {file_path}")
        try:
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext == '.pdf':
                logger.info("Processing PDF file")
                images = convert_from_path(file_path)
                text = ""
                for i, img in enumerate(images):
                    logger.info(f"Processing page {i+1}/{len(images)}")
                    page_text = pytesseract.image_to_string(img)
                    text += page_text + "\n\n"
                return text
            
            elif file_ext in ('.jpg', '.jpeg', '.png'):
                logger.info("Processing image file")
                return pytesseract.image_to_string(Image.open(file_path))
            
            elif file_ext == '.txt':
                logger.info("Processing text file")
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            else:
                raise ValueError(f"Unsupported file format: {file_ext}")
        
        except Exception as e:
            logger.error(f"Error during text extraction: {str(e)}")
            raise ValueError(f"Error during text extraction: {str(e)}")

    def parse_resume(self, text: str) -> Dict[str, str]:
        """
        Parses the resume text into sections.
        
        Args:
            text: The full text of the resume
            
        Returns:
            Dictionary with sections of the resume
        """
        logger.info("Parsing resume into sections")
        sections = {"skills": "", "experience": "", "education": "", "projects": "", "other": ""}
        current_section = "other"

        # Improved section header matching patterns
        section_headers = {
            'skills': r'^(skills|technical skills|proficiencies|core competencies|expertise|qualifications|technical expertise|key skills|technical proficiencies)',
            'experience': r'^(experience|work experience|professional experience|employment history|work history|career history|professional background|career experience)',
            'education': r'^(education|academic background|qualifications|degrees|educational background|academic qualifications|academic credentials)',
            'projects': r'^(projects|personal projects|portfolio|project experience|case studies|professional projects|selected projects)'
        }

        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:  # Skip empty lines
                continue

            # Check if the line is a section header
            section_found = False
            for section, pattern in section_headers.items():
                if re.match(pattern, line, re.IGNORECASE) and not re.search(r'[a-z]', line.strip()[:3]):
                    current_section = section
                    section_found = True
                    logger.debug(f"Found section: {section}")
                    break
            
            if not section_found:  # If not a section header, add to current section
                sections[current_section] += line + "\n"

        logger.info(f"Found sections: {', '.join([s for s, c in sections.items() if c.strip()])}")
        return sections

    def extract_keywords(self, text: str) -> List[str]:
        """
        Extracts keywords from text using SpaCy, handling multi-word keywords.
        
        Args:
            text: Text to extract keywords from
            
        Returns:
            List of extracted keywords
        """
        if not text.strip():
            return []
            
        doc = nlp(text.lower())
        keywords = []
        
        # Extract noun phrases (multi-word keywords)
        for chunk in doc.noun_chunks:
            # Lemmatize each word in the noun phrase
            lemmatized_chunk = " ".join([lemmatizer.lemmatize(token.text) for token in chunk])
            if lemmatized_chunk not in keywords:
                keywords.append(lemmatized_chunk)
        
        # Extract individual relevant tokens
        for token in doc:
            if (token.pos_ in ("NOUN", "PROPN", "ADJ", "VERB") and 
                not token.is_stop and 
                len(token.text) > 2):
                lemmatized_token = lemmatizer.lemmatize(token.text)
                if lemmatized_token not in keywords:
                    keywords.append(lemmatized_token)
        
        # Remove duplicate and clean up keywords
        clean_keywords = []
        for keyword in keywords:
            keyword = keyword.strip()
            if keyword and keyword not in clean_keywords:
                clean_keywords.append(keyword)
                
        return clean_keywords

    def identify_industry(self, job_desc_keywords: List[str]) -> str:
        """
        Identify which industry category the job belongs to.
        
        Args:
            job_desc_keywords: Keywords extracted from the job description
            
        Returns:
            The identified industry category
        """
        industry_matches = {}
        
        # For each industry, count how many keywords match
        for industry, industry_keywords in self.industry_keywords.items():
            matches = sum(1 for jk in job_desc_keywords 
                         if any(ik in jk or jk in ik for ik in industry_keywords))
            industry_matches[industry] = matches

        # Return industry with most matches
        if not industry_matches:
            return 'general'
            
        best_industry = max(industry_matches.items(), key=lambda x: x[1])
        logger.info(f"Identified industry: {best_industry[0]} with {best_industry[1]} keyword matches")
        return best_industry[0]

    def calculate_skills_score(self, resume_skills_text: str, job_desc_keywords: List[str]) -> Tuple[float, str, List[str]]:
        """
        Calculates the skills score.
        
        Args:
            resume_skills_text: The skills section from the resume
            job_desc_keywords: Keywords extracted from the job description
            
        Returns:
            Tuple of (score, feedback, suggestions)
        """
        logger.info("Calculating skills score")
        
        if not resume_skills_text.strip():
            return 0.0, "Skills section is empty or not found.", ["Add a dedicated skills section to your resume."]

        # Extract skills from the resume
        resume_skills = self.extract_keywords(resume_skills_text)
        if not resume_skills:
            return 0.0, "No recognizable skills found in the skills section.", ["Add specific, relevant skills to your skills section."]

        # Identify industry category
        industry_category = self.identify_industry(job_desc_keywords)
        industry_skills = self.industry_keywords.get(industry_category, [])

        # Find matching skills (using more flexible matching)
        matched_job_keywords = []
        for skill in resume_skills:
            for keyword in job_desc_keywords:
                if (skill in keyword or keyword in skill or 
                    self._calculate_similarity(skill, keyword) > 0.8):
                    matched_job_keywords.append(skill)
                    break
                    
        matched_industry_keywords = []
        for skill in resume_skills:
            for keyword in industry_skills:
                if (skill in keyword or keyword in skill or 
                    self._calculate_similarity(skill, keyword) > 0.8):
                    matched_industry_keywords.append(skill)
                    break

        # Calculate match ratios
        job_match_ratio = len(matched_job_keywords) / len(job_desc_keywords) if job_desc_keywords else 0
        industry_match_ratio = len(matched_industry_keywords) / len(industry_skills) if industry_skills else 0

        # Weight: 70% job-specific, 30% industry-standard
        score = (job_match_ratio * 0.7 + industry_match_ratio * 0.3) * 100
        score = min(score, 100.0)

        # Find missing important skills
        missing_skills = []
        for skill in industry_skills:
            if any(skill in keyword.lower() for keyword in job_desc_keywords):
                if not any(skill in s.lower() or s.lower() in skill for s in resume_skills):
                    missing_skills.append(skill)

        # Generate feedback
        feedback = f"Matched {len(matched_job_keywords)} of {len(job_desc_keywords)} job keywords and {len(matched_industry_keywords)} of {len(industry_skills)} industry keywords."
        
        # Generate suggestions
        suggestions = []
        if missing_skills and score < 90:
            top_missing = sorted(missing_skills, key=lambda s: sum(1 for k in job_desc_keywords if s in k), reverse=True)[:3]
            suggestions.append(f"Consider adding key skills like: {', '.join(top_missing)}")
            
        if score < 70:
            suggestions.append("Tailor your skills section specifically to this job description")
            
        if score < 50:
            suggestions.append("Reorganize your skills section to highlight the most relevant skills first")
            
        # If we can use Gemini API, get AI-powered suggestions
        if self.gemini_available and len(suggestions) < 3:
            ai_suggestions = self.get_gemini_suggestions("skills", resume_skills_text, self.job_description, score)
            for suggestion in ai_suggestions:
                if suggestion not in suggestions and len(suggestions) < 3:
                    suggestions.append(suggestion)
                    
        return score, feedback, suggestions[:3]  # Limit to 3 suggestions

    def calculate_experience_score(self, resume_experience_text: str, job_description: str) -> Tuple[float, str, List[str]]:
        """
        Calculates the experience score.
        
        Args:
            resume_experience_text: The experience section from the resume
            job_description: The full job description
            
        Returns:
            Tuple of (score, feedback, suggestions)
        """
        logger.info("Calculating experience score")
        
        if not resume_experience_text.strip():
            return 0.0, "Experience section is empty or not found.", ["Add a detailed work experience section."]

        # Check for required years of experience in job description
        years_required = 0
        years_pattern = re.search(r'(\d+)(?:\+)?\s*(?:-\s*\d+)?\s*years?(?:\s*of)?\s*experience', job_description, re.IGNORECASE)
        if years_pattern:
            years_required = int(years_pattern.group(1))
            logger.info(f"Job requires {years_required}+ years of experience")

        # Extract years of experience from resume
        years_exp = 0
        date_ranges = re.findall(r'(\d{4})\s*(?:-|to|–|—)\s*(?:present|current|now|(\d{4}))', resume_experience_text, re.IGNORECASE)
        for start, end in date_ranges:
            if start:
                start_year = int(start)
                end_year = int(end) if end else 2024  # Use current year if "present"
                years_exp += (end_year - start_year)
        
        # Check for quantifiable achievements
        has_metrics = bool(re.search(r'\d+(\.\d+)?%|\$\d+(\.\d+)?|\d+\s*(x|times|fold)|increased|decreased|improved|reduced|grew|saved', resume_experience_text, re.IGNORECASE))

        # Check for action verbs (expanded list)
        action_verbs = [
            'achieved', 'led', 'managed', 'developed', 'created', 'implemented',
            'designed', 'increased', 'decreased', 'improved', 'negotiated',
            'coordinated', 'supervised', 'trained', 'analyzed', 'built', 'launched',
            'delivered', 'optimized', 'reduced', 'generated', 'executed', 'initiated',
            'established', 'transformed', 'streamlined', 'spearheaded', 'orchestrated'
        ]
        verb_count = sum(1 for verb in action_verbs if re.search(r'\b' + verb + r'\b', resume_experience_text.lower()))
        good_verb_usage = verb_count >= 5

        # Calculate similarity with job responsibilities using TF-IDF and cosine similarity
        vectorizer = TfidfVectorizer()
        try:
            job_desc_resp = re.search(r"(?i)responsibilities:(.*)(?:requirements:|qualifications:|$)", job_description, re.DOTALL)
            if job_desc_resp:
                job_desc_resp_text = job_desc_resp.group(1).strip()
            else:
                job_desc_resp_text = job_description  # Use the whole job description as fallback

            tfidf_matrix = vectorizer.fit_transform([resume_experience_text, job_desc_resp_text])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        except Exception as e:
            logger.warning(f"Error calculating similarity: {e}")
            similarity = 0.5  # Default in case of error

        # Calculate experience score components
        years_score = min(30, (years_exp / max(1, years_required)) * 30) if years_required > 0 else 15
        relevance_score = similarity * 40  # 40% weight for relevance
        metrics_score = 20 if has_metrics else 0  # 20% weight for measurable achievements
        verb_score = 10 if good_verb_usage else (5 if verb_count > 0 else 0)  # 10% weight for action verbs

        score = years_score + relevance_score + metrics_score + verb_score
        score = min(score, 100.0)

        # Generate feedback and suggestions
        feedback = []
        suggestions = []
        
        if years_required > 0:
            if years_exp >= years_required:
                feedback.append(f"Your {years_exp} years of experience meets the requirement of {years_required}+ years.")
            else:
                feedback.append(f"Your {years_exp} years of experience is less than the required {years_required}+ years.")
                suggestions.append("Highlight other relevant experience or projects to compensate for the experience gap.")
                
        if not has_metrics:
            feedback.append("Your experience lacks quantifiable achievements.")
            suggestions.append("Quantify your accomplishments with specific metrics (%, $, numbers).")
            
        if not good_verb_usage:
            feedback.append("Your experience could use more strong action verbs.")
            suggestions.append("Start bullet points with strong action verbs like 'achieved', 'implemented', 'led'.")
            
        if similarity < 0.6:
            feedback.append("Your experience is not closely aligned with the job responsibilities.")
            suggestions.append("Tailor your experience bullet points to match the job responsibilities.")

        # If we can use Gemini API, get AI-powered suggestions
        if self.gemini_available and len(suggestions) < 3:
            ai_suggestions = self.get_gemini_suggestions("experience", resume_experience_text, self.job_description, score)
            for suggestion in ai_suggestions:
                if suggestion not in suggestions and len(suggestions) < 3:
                    suggestions.append(suggestion)

        return score, " ".join(feedback), suggestions[:3]

    def calculate_education_score(self, resume_education_text: str, job_description: str) -> Tuple[float, str, List[str]]:
        """
        Calculates the education score.
        
        Args:
            resume_education_text: The education section from the resume
            job_description: The full job description
            
        Returns:
            Tuple of (score, feedback, suggestions)
        """
        logger.info("Calculating education score")
        
        if not resume_education_text.strip():
            return 0.0, "Education section is empty or not found.", ["Add an education section with your degrees and relevant coursework."]

        # Check for required education level in job description
        edu_levels = {
            'phd': 5,
            'doctorate': 5,
            'master': 4,
            'ms': 4,
            'ma': 4,
            'mba': 4,
            'bachelor': 3,
            'bs': 3,
            'ba': 3,
            'bsc': 3,
            'associate': 2,
            'diploma': 1,
            'certificate': 1
        }
        
        # Find required education level in job description
        required_level = 0
        for edu, level in edu_levels.items():
            if re.search(r'\b' + edu + r'\b', job_description, re.IGNORECASE):
                required_level = max(required_level, level)
                
        # Find highest education level in resume
        resume_level = 0
        for edu, level in edu_levels.items():
            if re.search(r'\b' + edu + r'\b', resume_education_text, re.IGNORECASE):
                resume_level = max(resume_level, level)

        # Check for relevant coursework or projects
        relevant_keywords = self.extract_keywords(job_description)
        has_relevant_coursework = any(keyword in resume_education_text.lower() for keyword in relevant_keywords)

        # Calculate education score components
        if required_level > 0:
            # If specific education is required
            if resume_level >= required_level:
                level_score = 80
            else:
                level_score = 40  # Significant penalty for not meeting requirements
        else:
            # If no specific education is mentioned, use a sliding scale
            level_score = min(80, resume_level * 20)
            
        relevance_score = 20 if has_relevant_coursework else 0

        score = level_score + relevance_score
        score = min(score, 100.0)

        # Generate feedback and suggestions
        feedback = []
        suggestions = []
        
        if required_level > 0:
            level_names = {5: "PhD/Doctorate", 4: "Master's", 3: "Bachelor's", 2: "Associate's", 1: "Certificate/Diploma"}
            if resume_level >= required_level:
                feedback.append(f"Your {level_names.get(resume_level, 'degree')} meets the required education level.")
            else:
                feedback.append(f"Your education level ({level_names.get(resume_level, 'degree')}) is below the required {level_names.get(required_level, 'degree')}.")
                suggestions.append(f"Highlight relevant experience to compensate for the education requirement gap.")
                
        if not has_relevant_coursework:
            feedback.append("Your education section doesn't highlight relevant coursework or projects.")
            suggestions.append("Add relevant coursework, projects, or academic achievements that relate to the job.")
            
        if resume_level == 0:
            feedback.append("No clear degree information found in your education section.")
            suggestions.append("Clearly list your degrees with institution names and graduation years.")

        # If we can use Gemini API, get AI-powered suggestions
        if self.gemini_available and len(suggestions) < 3:
            ai_suggestions = self.get_gemini_suggestions("education", resume_education_text, self.job_description, score)
            for suggestion in ai_suggestions:
                if suggestion not in suggestions and len(suggestions) < 3:
                    suggestions.append(suggestion)

        return score, " ".join(feedback), suggestions[:3]

    def calculate_projects_score(self, resume_projects_text: str, job_description: str) -> Tuple[float, str, List[str]]:
        """
        Calculates the projects score.
        
        Args:
            resume_projects_text: The projects section from the resume
            job_description: The full job description
            
        Returns:
            Tuple of (score, feedback, suggestions)
        """
        logger.info("Calculating projects score")
        
        if not resume_projects_text.strip():
            return 0.0, "Projects section is empty or not found.", ["Add a projects section highlighting relevant work."]

        # Extract keywords from job description
        job_keywords = self.extract_keywords(job_description)
        project_keywords = self.extract_keywords(resume_projects_text)

        # Calculate relevance using TF-IDF and cosine similarity
        try:
            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform([resume_projects_text, job_description])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        except Exception as e:
            logger.warning(f"Error calculating project similarity: {e}")
            similarity = 0.5  # Default in case of error
            
        # Check for project descriptions and outcomes
        has_bullet_points = bool(re.search(r'[-•*]\s+\w+', resume_projects_text))
        has_outcomes = bool(re.search(r'\b(result|outcome|achieved|completed|delivered|created|built|developed|designed)\b', resume_projects_text, re.IGNORECASE))
        has_technologies = sum(1 for tech in ['python', 'java', 'c++', 'javascript', 'html', 'css', 'sql', 'react', 'angular', 'node', 'aws', 'cloud', 'database', 'api'] 
                               if re.search(r'\b' + tech + r'\b', resume_projects_text, re.IGNORECASE))

        # Calculate scores
        relevance_score = similarity * 60  # 60% weight for relevance
        description_score = 15 if has_bullet_points else 0  # 15% for formatting
        outcomes_score = 15 if has_outcomes else 0  # 15% for showing outcomes
        tech_score = min(10, has_technologies * 2)  # 10% for mentioning relevant technologies
        
        score = relevance_score + description_score + outcomes_score + tech_score
        score = min(score, 100.0)

        # Generate feedback and suggestions
        feedback = []
        suggestions = []
        
        if similarity < 0.6:
            feedback.append("Your projects are not closely aligned with the job requirements.")
            suggestions.append("Focus on projects that demonstrate skills relevant to this specific role.")
            
        if not has_bullet_points:
            feedback.append("Your project descriptions lack structured formatting.")
            suggestions.append("Use bullet points to clearly describe each project's purpose, your role, and technologies used.")
            
        if not has_outcomes:
            feedback.append("Your projects don't clearly show outcomes or impact.")
            suggestions.append("Describe what you achieved or delivered with each project and quantify results when possible.")
            
        if has_technologies < 3:
            feedback.append("Your projects don't highlight enough relevant technologies.")
            suggestions.append("Specifically mention the technologies, frameworks, and tools used in each project.")

        # If we can use Gemini API, get AI-powered suggestions
        if self.gemini_available and len(suggestions) < 3:
            ai_suggestions = self.get_gemini_suggestions("projects", resume_projects_text, self.job_description, score)
            for suggestion in ai_suggestions:
                if suggestion not in suggestions and len(suggestions) < 3:
                    suggestions.append(suggestion)

        return score, " ".join(feedback), suggestions[:3]

    def calculate_readability_score(self, resume_text: str) -> Tuple[float, str, List[str]]:
        """
        Calculates the readability score using established metrics.
        
        Args:
            resume_text: The full text of the resume
            
        Returns:
            Tuple of (score, feedback, suggestions)
        """
        logger.info("Calculating readability score")
        
        if not resume_text.strip():
            return 0.0, "No text to analyze for readability.", []

        sentences = nltk.sent_tokenize(resume_text)
        total_sentences = len(sentences)
        if total_sentences == 0:
            return 0.0, "No complete sentences found for readability analysis.", []

        # Calculate standard readability metrics
        try:
            flesch_reading_ease = textstat.flesch_reading_ease(resume_text)
            flesch_kincaid_grade = textstat.flesch_kincaid_grade(resume_text)
        except Exception as e:
            logger.warning(f"Error calculating readability metrics: {e}")
            flesch_reading_ease = 50
            flesch_kincaid_grade = 10

        # Check for passive voice (improved check)
        passive_voice_count = len(re.findall(r'\b(?:is|are|was|were|be|been|being)\s+\w+ed\b|\b(?:is|are|was|were|be|been|being)\s+\w+en\b', resume_text))
        passive_voice_ratio = passive_voice_count / total_sentences if total_sentences > 0 else 0

        # Check for bullet points
        bullet_points_count = len(re.findall(r'(?:\n\s*[-•*]|\n\s*\d+\.)', resume_text))
        
        # Check for jargon and overly complex words
        complex_words_count = textstat.difficult_words(resume_text)
        total_words = textstat.lexicon_count(resume_text)
        complex_ratio = complex_words_count / total_words if total_words > 0 else 0

        # Calculate readability score components
        ease_score = min(30, max(0, (flesch_reading_ease - 30) / 2))  # Target: 50-80 range (easy to read)
        grade_score = min(20, max(0, 20 - abs(flesch_kincaid_grade - 9)))  # Target: around grade 9
        passive_score = min(20, max(0, 20 - (passive_voice_ratio * 100)))  # Less passive voice is better
        structure_score = min(20, bullet_points_count)  # More bullet points up to 20
        complexity_score = min(10, max(0, 10 -(complex_ratio * 100)))  # Penalize high complexity

        score = ease_score + grade_score + passive_score + structure_score + complexity_score
        score = min(score, 100.0)

        # Generate feedback and suggestions
        feedback = []
        suggestions = []

        if flesch_reading_ease < 50:
            feedback.append("The readability of your resume is low.")
            suggestions.append("Use simpler language, shorter sentences, and more common words.")
        elif flesch_reading_ease > 80:
            feedback.append("The readability is extremely high; it might be too simplistic.")
            suggestions.append("Consider adding some technical terms appropriate for the role.") #Not too much though

        if flesch_kincaid_grade > 12:
            feedback.append("The reading grade level of your resume is high.")
            suggestions.append("Aim for a grade level closer to 9-11 to improve readability for a wider audience.")

        if passive_voice_ratio > 0.2:
            feedback.append("Your resume uses excessive passive voice.")
            suggestions.append("Rewrite sentences in active voice for stronger and clearer communication.")

        if bullet_points_count < 5:
            feedback.append("Your resume could benefit from more bullet points.")
            suggestions.append("Use bullet points to list key achievements, skills, and responsibilities.")

        if complex_ratio > 0.15:
            feedback.append("Your resume contains a high proportion of complex words.")
            suggestions.append("Replace some complex words with simpler alternatives, but maintain necessary technical terms.")

        # If we can use Gemini API, get AI-powered suggestions
        if self.gemini_available and len(suggestions) < 3:
            ai_suggestions = self.get_gemini_suggestions("readability", resume_text, self.job_description, score)
            for suggestion in ai_suggestions:
                if suggestion not in suggestions and len(suggestions) < 3:
                    suggestions.append(suggestion)
        return score, " ".join(feedback), suggestions[:3]

    def calculate_keywords_score(self, resume_text: str, job_keywords: List[str]) -> Tuple[float, List[str], List[str]]:
        """
        Calculates the overall keyword match score and identifies missing/present keywords.

        Args:
            resume_text: Full resume text.
            job_keywords: Keywords from the job description

        Returns:
            Tuple: (score, present_keywords, missing_keywords)
        """
        logger.info("Calculating keyword score")
        resume_keywords = self.extract_keywords(resume_text)

        present_keywords = []
        for rk in resume_keywords:
            for jk in job_keywords:
                if rk in jk or jk in rk or self._calculate_similarity(rk, jk) > 0.8:
                    present_keywords.append(rk)
                    break  # Avoid duplicates

        missing_keywords = []
        for jk in job_keywords:
            found = False
            for rk in resume_keywords:
                if jk in rk or rk in jk or self._calculate_similarity(rk, jk) > 0.8:
                    found = True
                    break
            if not found:
                missing_keywords.append(jk)


        score = (len(present_keywords) / len(job_keywords) * 100) if job_keywords else 0.0
        score = min(score, 100.0)

        logger.info(f"Keyword score: {score}, Present: {len(present_keywords)}, Missing: {len(missing_keywords)}")
        return score, present_keywords, missing_keywords


    def _calculate_similarity(self, word1: str, word2: str) -> float:
        """
        Calculates the similarity between two words using SpaCy's word vectors.

        Args:
            word1: First word
            word2: Second word

        Returns:
            Cosine similarity between the word vectors (0.0 to 1.0)
        """
        if not word1.strip() or not word2.strip():
            return 0.0

        vec1 = nlp(word1)
        vec2 = nlp(word2)
        
        # Check if vectors are valid (non-zero) before calculating similarity
        if vec1.has_vector and vec2.has_vector and vec1.vector_norm > 0 and vec2.vector_norm > 0:
            return vec1.similarity(vec2)
        else:
            logger.debug(f"No valid vector for: {word1} or {word2}")
            return 0.0  # Return 0 if vectors are not available

    def get_gemini_suggestions(self, section_name: str, section_text: str, job_description: str, score: float) -> List[str]:
        """
        Gets AI-powered suggestions from the Gemini API.

        Args:
            section_name: Name of resume section
            section_text: Text of the section
            job_description: Job description text
            score: Section score

        Returns:
            List of AI suggestions
        """
        if not self.gemini_available:
            return []

        prompt = f"""You are a professional resume reviewer and ATS expert.  Provide 3 concise, specific, and actionable suggestions to improve the following {section_name} section of a resume,
        given the job description and the current section score (out of 100). Focus on content improvements, not formatting.
        Do NOT suggest general formatting tips. Only focus on what can be improved from a content and ATS perspective.

        Resume Section ({section_name}, Score: {score:.1f}/100):
        {section_text}

        Job Description:
        {job_description}

        Suggestions:
        1.
        2.
        3.
        """
        try:
            response = self.gemini_model.generate_content(prompt, request_timeout=20)  # Add timeout

            # Extract suggestions (handle multi-line suggestions and variations)
            suggestions = []
            lines = response.text.split('\n')
            for line in lines:
                match = re.match(r'^[1-3]\.\s*(.*)', line)
                if match:
                    suggestion = match.group(1).strip()
                    if suggestion:
                        suggestions.append(suggestion)

            return suggestions

        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return ["Error: Could not get suggestions from the AI model."]


    def analyze(self, resume_path: str) -> Dict:
        """
        Analyzes the resume against the job description.

        Args:
             resume_path: Path to the resume

        Returns:
            A dictionary with the analysis
        """
        logger.info(f"Starting analysis of resume: {resume_path}")
        try:
            resume_text = self.extract_text(resume_path)
            parsed_resume = self.parse_resume(resume_text)

            # --- Section Analysis ---
            skills_score, skills_feedback, skills_suggestions = self.calculate_skills_score(parsed_resume['skills'], self.job_keywords)
            experience_score, experience_feedback, experience_suggestions = self.calculate_experience_score(parsed_resume['experience'], self.job_description)
            education_score, education_feedback, education_suggestions = self.calculate_education_score(parsed_resume['education'], self.job_description)
            projects_score, projects_feedback, projects_suggestions = self.calculate_projects_score(parsed_resume['projects'], self.job_description)
            readability_score, readability_feedback, readability_suggestions = self.calculate_readability_score(resume_text)
            keywords_score, present_keywords, missing_keywords = self.calculate_keywords_score(resume_text, self.job_keywords)

            # Other Section
            other_score = 50.0  # Default
            other_feedback = "This section contains information not categorized elsewhere. Ensure all relevant information is placed in standard sections."
            other_suggestions = ["Consider moving relevant details to standard sections (Skills, Experience, Education, Projects)."]

            # Check for missing sections
            missing_sections = [section for section in ["skills", "experience", "education", "projects"] if not parsed_resume[section].strip()]

            # --- Calculate Overall ATS Score (Weighted) ---
            total_score = (
                skills_score * self.weights['skills'] +
                experience_score * self.weights['experience'] +
                education_score * self.weights['education'] +
                projects_score * (self.weights['experience'] / 2) +  # Projects -> Experience
                readability_score * self.weights['readability'] +
                keywords_score * self.weights['keywords']

            )
            total_score = min(max(total_score, 0.0), 100.0)

            # --- Overall Feedback ---
            overall_feedback = ""
            if missing_sections:
                overall_feedback += f"Missing sections: {', '.join(missing_sections)}. "
            overall_feedback += (
                f"Resume matches {len(present_keywords)} of {len(self.job_keywords)} key terms. "
            )
            if total_score > 80:
                overall_feedback += "Excellent resume, well-tailored to the job description!"
            elif total_score > 60:
                overall_feedback += "Good resume, but consider making some improvements."
            else:
                overall_feedback += "Significant improvements are needed to align with the job description."

            # --- Construct JSON Output ---
            result = {
                "ats_score": round(total_score, 1),
                "overall_feedback": overall_feedback.strip(),
                "section_feedback": {
                    "skills": {
                        "score": round(skills_score, 1),
                        "feedback": skills_feedback,
                        "suggestions": skills_suggestions
                    },
                    "experience": {
                        "score": round(experience_score, 1),
                        "feedback": experience_feedback,
                        "suggestions": experience_suggestions
                    },
                    "education": {
                        "score": round(education_score, 1),
                        "feedback": education_feedback,
                        "suggestions": education_suggestions
                    },
                    "projects": {
                        "score": round(projects_score, 1),
                        "feedback": projects_feedback,
                        "suggestions": projects_suggestions
                    },
                    "other": {
                        "score": round(other_score, 1),
                        "feedback": other_feedback,
                        "suggestions": other_suggestions
                    }
                },
                "missing_sections": missing_sections,
                "keywords_feedback": {
                    "missing_keywords": missing_keywords[:10],  # Limit for brevity
                    "present_keywords": present_keywords[:10]
                }
            }
            return result

        except Exception as e:
            logger.exception("An error occurred during analysis")  # Logs traceback
            return {"error": str(e)}

def main():
    """
    Main function to run the ATS analysis.
    """
    parser = argparse.ArgumentParser(description="Analyze a resume against a job description.")
    parser.add_argument("resume_path", help="Path to the resume file (PDF, JPG, PNG, or TXT)")
    parser.add_argument("job_description_path", help="Path to the job description file (TXT)")
    args = parser.parse_args()

    # Check if paths are valid and files exist
    if not os.path.exists(args.resume_path):
        print(f"Error: Resume file not found at {args.resume_path}")
        return
    if not os.path.exists(args.job_description_path):
        print(f"Error: Job description file not found at {args.job_description_path}")
        return

    try:
        with open(args.job_description_path, 'r', encoding='utf-8') as f:
            job_description = f.read()

        ats = ResumeATS(job_description)
        result = ats.analyze(args.resume_path)
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()