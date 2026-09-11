"""
LegalLens Pro API v9.0
Complete backend met alle features
"""

import os
import re
import json
import uuid
import shutil
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Laad environment variabelen
load_dotenv()

# Configureer logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Database Setup ---
import sqlite3

DB_PATH = Path("data/legallens.db")

def init_db():
    """Initialiseer SQLite database"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # Dossiers tabel
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dossiers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                client TEXT,
                type TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Bestanden tabel
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                dossier_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                size INTEGER,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
            )
        ''')
        
        # Analyses tabel
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                dossier_id TEXT,
                document_type TEXT,
                summary TEXT,
                parties_involved TEXT,
                key_dates TEXT,
                risks TEXT,
                overall_advice TEXT,
                sentiment_score REAL,
                action_plan TEXT,
                negotiation_strategy TEXT,
                due_diligence_findings TEXT,
                time_saved_hours REAL,
                mode TEXT DEFAULT 'standard',
                analysis_type TEXT DEFAULT 'contract',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE SET NULL
            )
        ''')
        
        # Documenten tabel
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                dossier_id TEXT,
                content TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE SET NULL
            )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

# Initialiseer database
init_db()

def get_db():
    """Database connection helper"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- FastAPI App ---
app = FastAPI(
    title="LegalLens Pro API",
    description="Professionele AI juridische analyse platform",
    version="9.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount statische bestanden
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Configuratie ---
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
VALID_API_KEYS = os.getenv("VALID_API_KEYS", "demo-key,test-key").split(",")

# File storage
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# --- Pydantic Models ---
class RiskItem(BaseModel):
    clause_type: str
    severity: str
    description: str
    recommendation: str
    clause_quote: str = ""
    legal_reference: str = ""

class DueDiligenceFinding(BaseModel):
    category: str
    severity: str
    title: str
    description: str
    recommendation: str
    financial_impact: str = ""
    legal_reference: str = ""

class AnalysisResult(BaseModel):
    document_id: str
    summary: str
    contract_type: str
    parties_involved: List[str]
    key_dates: Dict[str, str]
    risks: List[RiskItem]
    overall_advice: str
    sentiment_score: float
    action_plan: Dict[str, List[str]] = {}
    negotiation_strategy: Dict[str, Any] = {}
    due_diligence_findings: List[DueDiligenceFinding] = []
    time_saved_hours: float = 0

class TextAnalysisRequest(BaseModel):
    text: str
    mode: str = "standard"
    analysis_type: str = "contract"

class LegalArticleRequest(BaseModel):
    article: str

class DossierCreate(BaseModel):
    name: str
    client: Optional[str] = None
    type: Optional[str] = None

class DocumentGenerateRequest(BaseModel):
    template_id: str
    dossier_id: Optional[str] = None
    custom_fields: Dict[str, str] = {}

# --- Document Templates ---
DOCUMENT_TEMPLATES = {
    "ingebrekestelling": {
        "id": "ingebrekestelling",
        "name": "Ingebrekestelling",
        "category": "Algemeen",
        "description": "Formele ingebrekestelling",
        "template_text": """{afzender_naam}
{afzender_adres}

{ontvanger_naam}
{ontvanger_adres}

{datum}

Betreft: Ingebrekestelling

Geachte {ontvanger_naam},

Hierbij stel ik u formeel in gebreke.

{beschrijving}

Met vriendelijke groet,

{afzender_naam}"""
    },
    "huurcontract": {
        "id": "huurcontract",
        "name": "Huurovereenkomst",
        "category": "Huurrecht",
        "description": "Standaard huurcontract",
        "template_text": """HUURCONTRACT

Verhuurder: {verhuurder_naam}
Huurder: {huurder_naam}
Object: {huurobject}
Huurprijs: € {huurprijs}
Startdatum: {start_datum}"""
    }
}

# --- Rechtspraak.nl API ---
class RechtspraakAPI:
    BASE_URL = "https://data.rechtspraak.nl/open-data/api"
    
    async def search_cases(self, article: str, max_results: int = 5) -> List[Dict]:
        try:
            params = {
                "q": article,
                "max": max_results,
                "sort": "date",
                "order": "desc"
            }
            
            response = requests.get(
                f"{self.BASE_URL}/search",
                params=params,
                timeout=10,
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            cases = []
            for result in data.get("Results", [])[:max_results]:
                content = result.get("Content", {})
                cases.append({
                    "ecli": content.get("Ecli", "Onbekend"),
                    "date": content.get("DatumUitspraak", "Onbekend"),
                    "court": content.get("Rechtspraak", {}).get("Naam", "Onbekend"),
                    "summary": content.get("Summary", {}).get("Value", ""),
                    "relevance": "hoog"
                })
            
            return cases
        except Exception as e:
            logger.error(f"Rechtspraak.nl error: {e}")
            return []

rechtspraak_api = RechtspraakAPI()

# --- Live Search ---
class LiveLegalSearch:
    def __init__(self):
        self.api_key = TAVILY_API_KEY
        self.available = bool(self.api_key)

    async def search_bw_text(self, article: str) -> str:
        if not self.available:
            return "Live search niet beschikbaar"
        
        try:
            headers = {"Content-Type": "application/json", "api-key": self.api_key}
            query = f"Artikel {article} Burgerlijk Wetboek site:wetten.overheid.nl"
            
            response = requests.post(
                "https://api.tavily.com/search",
                headers=headers,
                json={"query": query, "max_results": 1},
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("results"):
                return result["results"][0].get("content", "Tekst gevonden")
            return "Wettekst niet gevonden"
        except Exception as e:
            logger.error(f"Tavily error: {e}")
            return "Fout bij ophalen wettekst"

    async def search_case_law(self, article: str) -> List[Dict]:
        cases = await rechtspraak_api.search_cases(article)
        if cases:
            return cases
        
        if not self.available:
            return []
        
        try:
            headers = {"Content-Type": "application/json", "api-key": self.api_key}
            response = requests.post(
                "https://api.tavily.com/search",
                headers=headers,
                json={"query": f"Artikel {article} BW uitspraak"},
                timeout=10
            )
            response.raise_for_status()
            results = response.json()
            
            return [{"ecli": r.get('title'), "summary": r.get('content'), "relevance": "gemiddeld"} 
                    for r in results.get("results", [])]
        except:
            return []

live_search = LiveLegalSearch()

# --- AI Analyzer ---
class AIAnalyzer:
    def __init__(self):
        self.provider = AI_PROVIDER
    
    async def analyze_text(self, text: str, mode: str = "standard", analysis_type: str = "contract") -> Dict:
        if self.provider == "openai":
            return await self._analyze_with_openai(text, mode, analysis_type)
        return self._generate_mock_response(text)
    
    async def get_legal_commentary(self, article: str) -> Dict:
        bw_text = await live_search.search_bw_text(article)
        case_law = await live_search.search_case_law(article)
        
        return {
            "article": article,
            "title": f"Artikel {article}",
            "text": bw_text,
            "commentary": f"AI analyse van {article}",
            "jurisprudence": case_law
        }
    
    async def _analyze_with_openai(self, text: str, mode: str, analysis_type: str) -> Dict:
        try:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            
            system_prompt = "Je bent een Nederlandse jurist. Geef JSON response."
            user_prompt = f"Analyseer dit document: {text[:4000]}"
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            return json.loads(result["choices"][0]["message"]["content"])
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return self._generate_mock_response(text)
    
    def _generate_mock_response(self, text: str) -> Dict:
        return {
            "summary": "Analyse van document",
            "contract_type": "Onbekend",
            "parties_involved": ["Partij A", "Partij B"],
            "key_dates": {},
            "risks": [],
            "overall_advice": "Advies",
            "sentiment_score": 0.5,
            "action_plan": {},
            "negotiation_strategy": {},
            "due_diligence_findings": [],
            "time_saved_hours": 1.0
        }

analyzer = AIAnalyzer()

# --- Helper Functions ---
def normalize_article(article: str) -> str:
    article = re.sub(r'^Art\.\s*', '', article, flags=re.IGNORECASE)
    article = re.sub(r'^Artikel\s*', '', article, flags=re.IGNORECASE)
    article = ' '.join(article.split())
    if not any(x in article.upper() for x in ['BW', 'SR', 'AWB']):
        article = article + ' BW'
    return article

async def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    if api_key and api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key or "public"

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": "9.0.0",
        "database": "connected" if DB_PATH.exists() else "not connected"
    }

@app.post("/api/analyze-text", response_model=AnalysisResult)
async def analyze_text(request: TextAnalysisRequest, api_key: str = Depends(verify_api_key)):
    if not request.text or len(request.text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Text too short")
    
    result = await analyzer.analyze_text(request.text, request.mode, request.analysis_type)
    result["document_id"] = str(uuid.uuid4())
    
    # Save to database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO analyses (id, document_type, summary, parties_involved, key_dates, 
           risks, overall_advice, sentiment_score, action_plan, negotiation_strategy,
           due_diligence_findings, time_saved_hours, mode, analysis_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (result["document_id"], result.get("contract_type", ""), result.get("summary", ""),
         json.dumps(result.get("parties_involved", [])), json.dumps(result.get("key_dates", {})),
         json.dumps(result.get("risks", [])), result.get("overall_advice", ""),
         result.get("sentiment_score", 0.5), json.dumps(result.get("action_plan", {})),
         json.dumps(result.get("negotiation_strategy", {})),
         json.dumps(result.get("due_diligence_findings", [])),
         result.get("time_saved_hours", 0), request.mode, request.analysis_type)
    )
    conn.commit()
    conn.close()
    
    return AnalysisResult(**result)

@app.post("/api/analyze-file", response_model=AnalysisResult)
async def analyze_file(
    file: UploadFile = File(...),
    mode: str = Form("standard"),
    analysis_type: str = Form("contract"),
    api_key: str = Depends(verify_api_key)
):
    if not file.filename.endswith(('.pdf', '.txt', '.docx')):
        raise HTTPException(status_code=400, detail="Only PDF, TXT, DOCX")
    
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    temp_path = UPLOAD_DIR / f"temp_{file_id}{file_ext}"
    
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    try:
        text = ""
        if file.filename.endswith('.txt'):
            with open(temp_path, 'r', encoding='utf-8') as f:
                text = f.read()
        elif file.filename.endswith('.pdf'):
            try:
                import PyPDF2
                with open(temp_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "\n".join([page.extract_text() or "" for page in reader.pages])
            except:
                raise HTTPException(status_code=500, detail="PDF error")
        
        if len(text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Not enough text")
        
        result = await analyzer.analyze_text(text, mode, analysis_type)
        result["document_id"] = str(uuid.uuid4())
        
        temp_path.unlink()
        
        return AnalysisResult(**result)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/legal-commentary")
async def get_legal_commentary(request: LegalArticleRequest, api_key: str = Depends(verify_api_key)):
    article = normalize_article(request.article.strip())
    return await analyzer.get_legal_commentary(article)

@app.get("/api/templates")
async def list_templates(api_key: str = Depends(verify_api_key)):
    return {"templates": list(DOCUMENT_TEMPLATES.values())}

@app.post("/api/templates/generate")
async def generate_document(request: DocumentGenerateRequest, api_key: str = Depends(verify_api_key)):
    if request.template_id not in DOCUMENT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template = DOCUMENT_TEMPLATES[request.template_id]
    content = template["template_text"]
    
    for key, value in request.custom_fields.items():
        content = content.replace(f"{{{key}}}", value)
    
    doc_id = str(uuid.uuid4())
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO documents (id, template_id, dossier_id, content, title) VALUES (?, ?, ?, ?, ?)",
        (doc_id, request.template_id, request.dossier_id, content, template["name"])
    )
    conn.commit()
    conn.close()
    
    return {"document_id": doc_id, "content": content, "title": template["name"]}

@app.get("/api/documents")
async def list_documents(api_key: str = Depends(verify_api_key)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents ORDER BY created_at DESC")
    docs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"documents": docs}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
