"""
LegalLens Pro API v9.0
Robuuste backend met SQLite, Rechtspraak.nl API, en RAG-architectuur
"""

import os
import re
import json
import uuid
import shutil
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Laad environment variabelen
load_dotenv()

# Configureer logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Database Setup (SQLite) ---
import sqlite3

DB_PATH = Path("data/legallens.db")

def init_db():
    """Initialiseer SQLite database"""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")
    
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
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

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
    version="9.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
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

# File storage directory
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

class DossierUpdate(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None

# --- Rechtspraak.nl API (GRATIS) ---
class RechtspraakAPI:
    """Directe koppeling met Rechtspraak.nl Open Data API"""
    
    BASE_URL = "https://data.rechtspraak.nl/open-data/api"
    
    def __init__(self):
        self.available = True
        logger.info("Rechtspraak.nl API initialized")
    
    async def search_cases(self, article: str, max_results: int = 5) -> List[Dict]:
        """Zoek jurisprudentie via Rechtspraak.nl API"""
        try:
            query = f"{article}"
            params = {
                "q": query,
                "max": max_results,
                "type": "Rechtspraak.Uitspraken",
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
            results = data.get("Results", [])
            
            for result in results[:max_results]:
                content = result.get("Content", {})
                cases.append({
                    "ecli": content.get("Ecli", "Onbekend"),
                    "date": content.get("DatumUitspraak", "Onbekend"),
                    "court": content.get("Rechtspraak", {}).get("Naam", "Onbekende rechtbank"),
                    "summary": content.get("Summary", {}).get("Value", "Geen samenvatting"),
                    "title": content.get("Title", {}).get("Value", "Onbekende zaak"),
                    "relevance": "hoog",
                    "url": f"https://uitspraken.rechtspraak.nl/#!/details?id={content.get('Ecli', '')}"
                })
            
            return cases
            
        except Exception as e:
            logger.error(f"Rechtspraak.nl API error: {e}")
            return []

# --- Live Search Engine (Tavily) ---
class LiveLegalSearch:
    """Zoekmachine voor live wettekst en jurisprudentie"""
    
    def __init__(self):
        self.api_key = TAVILY_API_KEY
        self.available = bool(self.api_key)
        if not self.available:
            logger.warning("Tavily API key niet gevonden - alleen database beschikbaar")

    async def search_bw_text(self, article: str) -> str:
        """Zoek wettekst op via wetten.overheid.nl of Tavily"""
        if not self.available:
            return "Live search niet beschikbaar (geen Tavily API key)"
        
        try:
            headers = {"Content-Type": "application/json", "api-key": self.api_key}
            query = f"Artikel {article} Burgerlijk Wetboek volledige tekst site:wetten.overheid.nl"
            payload = {
                "query": query,
                "search_depth": "basic",
                "max_results": 1,
                "include_answer": True
            }
            
            response = requests.post(
                "https://api.tavily.com/search",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("results"):
                return result["results"][0].get("content", "Tekst gevonden")
            return "Wettekst niet gevonden"
            
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return "Fout bij ophalen wettekst"

    async def search_case_law(self, article: str) -> List[Dict]:
        """Zoek jurisprudentie - eerst Rechtspraak.nl, dan Tavily als fallback"""
        
        # 1. Probeer eerst Rechtspraak.nl (gratis, gestructureerd)
        cases = await rechtspraak_api.search_cases(article, max_results=3)
        
        if cases:
            logger.info(f"Found {len(cases)} cases from Rechtspraak.nl")
            return cases
        
        # 2. Fallback naar Tavily als Rechtspraak.nl niets oplevert
        if not self.available:
            return []
        
        try:
            headers = {"Content-Type": "application/json", "api-key": self.api_key}
            query = f"Artikel {article} BW uitspraak rechtspraak.nl"
            payload = {
                "query": query,
                "search_depth": "basic",
                "max_results": 3
            }
            
            response = requests.post(
                "https://api.tavily.com/search",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            results = response.json()
            
            cases = []
            for r in results.get("results", []):
                cases.append({
                    "ecli": r.get('title', 'Onbekende zaak'),
                    "date": "Recent",
                    "court": "Rechtspraak.nl",
                    "summary": r.get('content', ''),
                    "relevance": "gemiddeld",
                    "url": r.get('url', '')
                })
            return cases
            
        except Exception as e:
            logger.error(f"Case law search error: {e}")
            return []

# Initialiseer
rechtspraak_api = RechtspraakAPI()
live_search = LiveLegalSearch()

# --- AI Analyzer ---
class AIAnalyzer:
    """Hoofdklasse voor AI analyse"""
    
    def __init__(self):
        self.provider = AI_PROVIDER
    
    async def analyze_text(self, text: str, mode: str = "standard", analysis_type: str = "contract") -> Dict:
        """Analyseer juridische tekst"""
        logger.info(f"Analyzing text with mode={mode}, type={analysis_type}")
        
        if self.provider == "openai":
            return await self._analyze_with_openai(text, mode, analysis_type)
        elif self.provider == "huggingface":
            return await self._analyze_with_huggingface(text, mode, analysis_type)
        return self._generate_mock_response(text)
    
    async def get_legal_commentary(self, article: str) -> Dict:
        """Haal wettekst + AI commentaar op (RAG model)"""
        logger.info(f"Looking up article: {article}")
        
        # RAG: Haal live data op
        bw_text = await self._get_bw_text(article)
        case_law = await self._get_case_law(article)
        
        # Genereer commentaar op basis van live data
        commentary = await self._generate_commentary(article, bw_text)
        
        return {
            "article": article,
            "title": f"Artikel {article}",
            "text": bw_text,
            "commentary": commentary,
            "related": [],  # Kan dynamisch opgehaald worden
            "history": [],  # Kan dynamisch opgehaald worden
            "jurisprudence": case_law
        }
    
    async def _get_bw_text(self, article: str) -> str:
        """Haal wettekst op (RAG: dynamisch ophalen)"""
        return await live_search.search_bw_text(article)
    
    async def _get_case_law(self, article: str) -> List[Dict]:
        """Haal jurisprudentie op (RAG: dynamisch ophalen)"""
        return await live_search.search_case_law(article)
    
    async def _generate_commentary(self, article: str, bw_text: str) -> str:
        """Genereer AI commentaar op basis van wettekst"""
        try:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            prompt = f"""Je bent een ervaren Nederlandse jurist. Geef een beknopte, praktische uitleg van:

**{article}**

Wettekst:
{bw_text}

Geef in 2-3 zinnen:
1. Wat betekent dit artikel in de praktijk?
2. Hoe passen rechters dit toe?
3. Wat zijn de belangrijkste valkuilen?

Geef ALLEEN de uitleg, geen inleiding."""

            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Je bent een Nederlandse jurist."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 300
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"AI commentary error: {e}")
            return "AI commentaar niet beschikbaar. Raadpleeg een juridische database."
    
    async def _analyze_with_openai(self, text: str, mode: str, analysis_type: str) -> Dict:
        """Analyseer met OpenAI"""
        try:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            system_prompt = self._get_system_prompt(mode)
            user_prompt = self._get_user_prompt(text, analysis_type)
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 3000,
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
            
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            
            word_count = len(text.split())
            parsed["time_saved_hours"] = round(word_count / 500 * 0.5, 1)
            
            return parsed
            
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return self._generate_mock_response(text)
    
    def _get_system_prompt(self, mode: str) -> str:
        """Krijg system prompt"""
        if mode == "advocaat":
            return """Je bent een ervaren Nederlandse advocaat met 20 jaar praktijkervaring.
Je analyseert documenten grondig, citeert specifieke wetsartikelen en jurisprudentie,
en geeft strategisch advies op professioneel niveau.

BELANGRIJKE REGELS:
1. Geef ALLEEN een JSON response, geen andere tekst
2. Gebruik juridisch Nederlands en Latijnse termen waar passend
3. Citeer SPECIFIEKE wetsartikelen (BW, Sr, Awb, etc.)
4. Verwijs naar relevante jurisprudentie (ECLI nummers)
5. Geef concrete processtrategieën
6. Kwantificeer financiële impact waar mogelijk
7. Wees kritisch en signaleer ALLE risico's"""
        else:
            return """Je bent een ervaren Nederlandse jurist gespecialiseerd in contractanalyse.
Je analyseert documenten grondig en geeft concrete, bruikbare adviezen.

BELANGRIJKE REGELS:
1. Geef ALLEEN een JSON response, geen andere tekst
2. Baseer ALLES op de feitelijke inhoud van het document
3. Noem concrete namen, bedragen en data uit het document
4. Geef bij elk risico een citaat uit het document
5. Wees specifiek in je adviezen"""
    
    def _get_user_prompt(self, text: str, analysis_type: str) -> str:
        """Krijg user prompt"""
        return f"""Analyseer het volgende juridische document:

=== DOCUMENT ===
{text[:8000]}
=== EINDE DOCUMENT ===

Geef een JSON response met deze EXACTE structuur:

{{
  "summary": "Gedetailleerde samenvatting van 3-5 zinnen",
  "contract_type": "Type document",
  "parties_involved": ["Volledige naam partij 1", "Volledige naam partij 2"],
  "key_dates": {{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}},
  "risks": [
    {{
      "clause_type": "Type clausule",
      "severity": "Low/Medium/High/Critical",
      "description": "Specifieke beschrijving",
      "recommendation": "Concreet advies",
      "clause_quote": "Letterlijk citaat",
      "legal_reference": "Relevant wetsartikel (bijv: Art. 6:94 BW)"
    }}
  ],
  "overall_advice": "Algemeen advies in 2-3 zinnen",
  "sentiment_score": 0.0-1.0,
  "action_plan": {{
    "direct": ["Actie 1", "Actie 2"],
    "short_term": ["Actie 1", "Actie 2"],
    "long_term": ["Actie 1", "Actie 2"]
  }},
  "negotiation_strategy": {{
    "your_position": "Zwak/Gemiddeld/Sterk",
    "counterparty_position": "Zwak/Gemiddeld/Sterk",
    "arguments": ["Argument 1", "Argument 2"],
    "alternatives": ["Alternatief 1", "Alternatief 2"],
    "fallback": "Fallback positie"
  }}
}}

BELANGRIJK: Geef ALLEEN de JSON, geen andere tekst"""
    
    async def _analyze_with_huggingface(self, text: str, mode: str, analysis_type: str) -> Dict:
        """Analyseer met HuggingFace"""
        try:
            API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct"
            headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
            
            prompt = f"""Analyseer dit document: {text[:4000]}
Geef JSON met: summary, contract_type, parties_involved, key_dates, risks, overall_advice, sentiment_score, action_plan, negotiation_strategy"""
            
            payload = {
                "inputs": prompt,
                "parameters": {"max_new_tokens": 2000, "return_full_text": False}
            }
            
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            result = response.json()
            
            generated_text = result[0]["generated_text"] if isinstance(result, list) else result.get("generated_text", "")
            
            json_start = generated_text.find("{")
            json_end = generated_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(generated_text[json_start:json_end])
                parsed["time_saved_hours"] = 2.0
                return parsed
                
        except Exception as e:
            logger.error(f"HuggingFace error: {e}")
        
        return self._generate_mock_response(text)
    
    def _generate_mock_response(self, text: str) -> Dict:
        """Genereer mock response"""
        return {
            "summary": f"Analyse van {len(text)} tekens",
            "contract_type": "Onbekend",
            "parties_involved": ["Partij A", "Partij B"],
            "key_dates": {"start_date": "niet gevonden"},
            "risks": [],
            "overall_advice": "Gebruik OpenAI voor echte analyse",
            "sentiment_score": 0.5,
            "action_plan": {"direct": [], "short_term": [], "long_term": []},
            "negotiation_strategy": {"your_position": "Onbekend", "counterparty_position": "Onbekend", "arguments": [], "alternatives": [], "fallback": ""},
            "due_diligence_findings": [],
            "time_saved_hours": 0
        }

analyzer = AIAnalyzer()

# --- Helper Functies ---
def normalize_article(article: str) -> str:
    """Normaliseer artikel naam"""
    article = re.sub(r'^Art\.\s*', '', article, flags=re.IGNORECASE)
    article = re.sub(r'^Artikel\s*', '', article, flags=re.IGNORECASE)
    article = ' '.join(article.split())
    if not any(x in article.upper() for x in ['BW', 'SR', 'AWB']):
        article = article + ' BW'
    return article

async def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verifieer API key"""
    if api_key and api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key or "public"

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve frontend"""
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "provider": AI_PROVIDER,
        "tavily_available": live_search.available,
        "rechtspraak_available": rechtspraak_api.available,
        "version": "9.0.0",
        "database": "connected" if DB_PATH.exists() else "not connected"
    }

# --- Dossier Endpoints ---

@app.post("/api/dossiers")
async def create_dossier(
    dossier: DossierCreate,
    api_key: str = Depends(verify_api_key)
):
    """Maak nieuw dossier aan"""
    dossier_id = str(uuid.uuid4())
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO dossiers (id, name, client, type) VALUES (?, ?, ?, ?)",
        (dossier_id, dossier.name, dossier.client, dossier.type)
    )
    conn.commit()
    conn.close()
    
    logger.info(f"Dossier created: {dossier_id}")
    
    return {
        "id": dossier_id,
        "name": dossier.name,
        "client": dossier.client,
        "type": dossier.type,
        "status": "active",
        "created_at": datetime.now().isoformat()
    }

@app.get("/api/dossiers")
async def list_dossiers(
    api_key: str = Depends(verify_api_key)
):
    """Haal alle dossiers op"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dossiers ORDER BY created_at DESC")
    dossiers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"dossiers": dossiers, "total": len(dossiers)}

@app.get("/api/dossiers/{dossier_id}")
async def get_dossier(
    dossier_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Haal dossier details op"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dossiers WHERE id = ?", (dossier_id,))
    dossier = cursor.fetchone()
    
    if not dossier:
        conn.close()
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")
    
    # Haal bestanden op
    cursor.execute("SELECT * FROM files WHERE dossier_id = ?", (dossier_id,))
    files = [dict(row) for row in cursor.fetchall()]
    
    # Haal analyses op
    cursor.execute("SELECT * FROM analyses WHERE dossier_id = ?", (dossier_id,))
    analyses = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        **dict(dossier),
        "files": files,
        "analyses": analyses
    }

@app.put("/api/dossiers/{dossier_id}")
async def update_dossier(
    dossier_id: str,
    dossier: DossierUpdate,
    api_key: str = Depends(verify_api_key)
):
    """Update dossier"""
    conn = get_db()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if dossier.name:
        updates.append("name = ?")
        params.append(dossier.name)
    if dossier.client:
        updates.append("client = ?")
        params.append(dossier.client)
    if dossier.type:
        updates.append("type = ?")
        params.append(dossier.type)
    if dossier.status:
        updates.append("status = ?")
        params.append(dossier.status)
    
    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(dossier_id)
    
    cursor.execute(f"UPDATE dossiers SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    
    return {"message": "Dossier updated"}

@app.delete("/api/dossiers/{dossier_id}")
async def delete_dossier(
    dossier_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Verwijder dossier"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dossiers WHERE id = ?", (dossier_id,))
    conn.commit()
    conn.close()
    
    logger.info(f"Dossier deleted: {dossier_id}")
    
    return {"message": "Dossier deleted"}

# --- File Upload Endpoints ---

@app.post("/api/dossiers/{dossier_id}/files")
async def upload_file_to_dossier(
    dossier_id: str,
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key)
):
    """Upload bestand naar dossier"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM dossiers WHERE id = ?", (dossier_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")
    
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    saved_filename = f"{file_id}{file_ext}"
    file_path = UPLOAD_DIR / saved_filename
    
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    cursor.execute(
        "INSERT INTO files (id, dossier_id, filename, original_name, size) VALUES (?, ?, ?, ?, ?)",
        (file_id, dossier_id, saved_filename, file.filename, file.size)
    )
    conn.commit()
    conn.close()
    
    logger.info(f"File uploaded: {file_id} to dossier {dossier_id}")
    
    return {
        "id": file_id,
        "filename": saved_filename,
        "original_name": file.filename,
        "size": file.size,
        "uploaded_at": datetime.now().isoformat()
    }

@app.get("/api/dossiers/{dossier_id}/files")
async def list_dossier_files(
    dossier_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Haal alle bestanden van een dossier op"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE dossier_id = ? ORDER BY uploaded_at DESC", (dossier_id,))
    files = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"files": files, "total": len(files)}

# --- Analyse Endpoints ---

@app.post("/api/analyze-text", response_model=AnalysisResult)
async def analyze_text(
    request: TextAnalysisRequest,
    dossier_id: Optional[str] = None,
    api_key: str = Depends(verify_api_key)
):
    """Analyseer tekst"""
    text = request.text
    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Text too short (min 50 characters)")
    
    try:
        result = await analyzer.analyze_text(text, request.mode, request.analysis_type)
        
        # Save to database
        analysis_id = str(uuid.uuid4())
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO analyses 
            (id, dossier_id, document_type, summary, parties_involved, key_dates, 
             risks, overall_advice, sentiment_score, action_plan, negotiation_strategy,
             due_diligence_findings, time_saved_hours, mode, analysis_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis_id,
                dossier_id,
                result.get("contract_type", ""),
                result.get("summary", ""),
                json.dumps(result.get("parties_involved", [])),
                json.dumps(result.get("key_dates", {})),
                json.dumps(result.get("risks", [])),
                result.get("overall_advice", ""),
                result.get("sentiment_score", 0.5),
                json.dumps(result.get("action_plan", {})),
                json.dumps(result.get("negotiation_strategy", {})),
                json.dumps(result.get("due_diligence_findings", [])),
                result.get("time_saved_hours", 0),
                request.mode,
                request.analysis_type
            )
        )
        conn.commit()
        conn.close()
        
        result["document_id"] = analysis_id
        logger.info(f"Analysis completed: {analysis_id}")
        
        return AnalysisResult(**result)
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/analyze-file", response_model=AnalysisResult)
async def analyze_file(
    file: UploadFile = File(...),
    dossier_id: Optional[str] = Form(None),
    mode: str = Form("standard"),
    analysis_type: str = Form("contract"),
    api_key: str = Depends(verify_api_key)
):
    """Analyseer geüpload bestand"""
    if not file.filename.endswith(('.pdf', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files supported")
    
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    temp_path = UPLOAD_DIR / f"temp_{file_id}{file_ext}"
    
    with open(temp_path, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    
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
                    text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            except ImportError:
                raise HTTPException(status_code=500, detail="PDF support not configured")
        else:
            raise HTTPException(status_code=400, detail="File type not supported")
        
        if not text or len(text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Could not extract enough text")
        
        result = await analyzer.analyze_text(text, mode, analysis_type)
        
        analysis_id = str(uuid.uuid4())
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO analyses 
            (id, dossier_id, document_type, summary, parties_involved, key_dates, 
             risks, overall_advice, sentiment_score, action_plan, negotiation_strategy,
             due_diligence_findings, time_saved_hours, mode, analysis_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis_id,
                dossier_id,
                result.get("contract_type", ""),
                result.get("summary", ""),
                json.dumps(result.get("parties_involved", [])),
                json.dumps(result.get("key_dates", {})),
                json.dumps(result.get("risks", [])),
                result.get("overall_advice", ""),
                result.get("sentiment_score", 0.5),
                json.dumps(result.get("action_plan", {})),
                json.dumps(result.get("negotiation_strategy", {})),
                json.dumps(result.get("due_diligence_findings", [])),
                result.get("time_saved_hours", 0),
                mode,
                analysis_type
            )
        )
        
        if dossier_id:
            saved_filename = f"{file_id}{file_ext}"
            final_path = UPLOAD_DIR / saved_filename
            temp_path.rename(final_path)
            
            cursor.execute(
                "INSERT INTO files (id, dossier_id, filename, original_name, size) VALUES (?, ?, ?, ?, ?)",
                (file_id, dossier_id, saved_filename, file.filename, file.size)
            )
        else:
            temp_path.unlink()
        
        conn.commit()
        conn.close()
        
        result["document_id"] = analysis_id
        logger.info(f"File analysis completed: {analysis_id}")
        
        return AnalysisResult(**result)
        
    except Exception as e:
        logger.error(f"File analysis failed: {e}")
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analyses")
async def list_analyses(
    dossier_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    api_key: str = Depends(verify_api_key)
):
    """Haal analyses op"""
    conn = get_db()
    cursor = conn.cursor()
    
    if dossier_id:
        cursor.execute(
            "SELECT * FROM analyses WHERE dossier_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (dossier_id, limit, offset)
        )
    else:
        cursor.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
    
    analyses = []
    for row in cursor.fetchall():
        analysis = dict(row)
        for field in ['parties_involved', 'key_dates', 'risks', 'action_plan', 
                      'negotiation_strategy', 'due_diligence_findings']:
            if analysis.get(field):
                try:
                    analysis[field] = json.loads(analysis[field])
                except:
                    analysis[field] = []
        analyses.append(analysis)
    
    conn.close()
    
    return {"analyses": analyses, "total": len(analyses)}

@app.get("/api/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Haal analyse details op"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    analysis = cursor.fetchone()
    
    if not analysis:
        conn.close()
        raise HTTPException(status_code=404, detail="Analyse niet gevonden")
    
    analysis_dict = dict(analysis)
    
    for field in ['parties_involved', 'key_dates', 'risks', 'action_plan', 
                  'negotiation_strategy', 'due_diligence_findings']:
        if analysis_dict.get(field):
            try:
                analysis_dict[field] = json.loads(analysis_dict[field])
            except:
                analysis_dict[field] = []
    
    conn.close()
    
    return analysis_dict

@app.delete("/api/analyses/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Verwijder analyse"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    conn.commit()
    conn.close()
    
    logger.info(f"Analysis deleted: {analysis_id}")
    
    return {"message": "Analyse verwijderd"}

# --- Legal Commentary Endpoint ---

@app.post("/api/legal-commentary")
async def get_legal_commentary(
    request: LegalArticleRequest,
    api_key: str = Depends(verify_api_key)
):
    """Haal wettekst + AI commentaar op"""
    article = normalize_article(request.article.strip())
    
    try:
        result = await analyzer.get_legal_commentary(article)
        return result
    except Exception as e:
        logger.error(f"Legal commentary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/statistics")
async def get_statistics(
    api_key: str = Depends(verify_api_key)
):
    """Haal statistieken op"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM dossiers WHERE status = 'active'")
    active_dossiers = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM analyses")
    total_analyses = cursor.fetchone()['count']
    
    cursor.execute("SELECT SUM(time_saved_hours) as total FROM analyses")
    total_hours = cursor.fetchone()['total'] or 0
    
    conn.close()
    
    return {
        "active_dossiers": active_dossiers,
        "total_analyses": total_analyses,
        "total_hours_saved": round(total_hours, 1)
    }

# --- Document Drafter Models ---
class DocumentTemplate(BaseModel):
    id: str
    name: str
    category: str
    description: str
    fields: List[Dict[str, str]]
    template_text: str

class DocumentGenerateRequest(BaseModel):
    template_id: str
    dossier_id: Optional[str] = None
    custom_fields: Dict[str, str] = {}
    analysis_id: Optional[str] = None

class DocumentGenerateResponse(BaseModel):
    document_id: str
    content: str
    title: str
    created_at: str

# --- Document Templates Database ---
DOCUMENT_TEMPLATES = {
    "ingebrekestelling": {
        "id": "ingebrekestelling",
        "name": "Ingebrekestelling",
        "category": "Algemeen",
        "description": "Formele ingebrekestelling voor wanprestatie",
        "fields": [
            {"name": "afzender_naam", "label": "Naam afzender", "type": "text"},
            {"name": "afzender_adres", "label": "Adres afzender", "type": "text"},
            {"name": "ontvanger_naam", "label": "Naam ontvanger", "type": "text"},
            {"name": "ontvanger_adres", "label": "Adres ontvanger", "type": "text"},
            {"name": "datum", "label": "Datum", "type": "date"},
            {"name": "contract_datum", "label": "Datum overeenkomst", "type": "date"},
            {"name": "beschrijving_verplichting", "label": "Beschrijving verplichting", "type": "textarea"},
            {"name": "termijn_dagen", "label": "Termijn (dagen)", "type": "number", "default": "14"},
        ],
        "template_text": """{afzender_naam}
{afzender_adres}

{ontvanger_naam}
{ontvanger_adres}

{datum}

Betreft: Ingebrekestelling

Geachte {ontvanger_naam},

Hierbij stel ik u formeel in gebreke met betrekking tot de verplichtingen voortvloeiend uit de overeenkomst d.d. {contract_datum}.

Ondanks herhaaldelijke verzoeken heeft u nagelaten om:
{beschrijving_verplichting}

Ik verzoek u om binnen {termijn_dagen} dagen na ontvangst van deze brief alsnog te voldoen aan uw verplichtingen.

Mocht u binnen deze termijn niet aan uw verplichtingen voldoen, dan behoud ik mij het recht voor om over te gaan tot verdere juridische stappen, waaronder maar niet beperkt tot ontbinding van de overeenkomst en het vorderen van schadevergoeding.

Ik vertrouw erop dat u deze zaak serieus zult nemen en zie uw reactie tegemoet.

Met vriendelijke groet,

{afzender_naam}"""
    },
    
    "huurcontract": {
        "id": "huurcontract",
        "name": "Huurovereenkomst",
        "category": "Huurrecht",
        "description": "Standaard huurovereenkomst voor woonruimte",
        "fields": [
            {"name": "verhuurder_naam", "label": "Naam verhuurder", "type": "text"},
            {"name": "verhuurder_adres", "label": "Adres verhuurder", "type": "text"},
            {"name": "huurder_naam", "label": "Naam huurder", "type": "text"},
            {"name": "huurder_adres", "label": "Adres huurder", "type": "text"},
            {"name": "huurobject", "label": "Adres gehuurde woning", "type": "text"},
            {"name": "huurprijs", "label": "Maandelijkse huurprijs (€)", "type": "number"},
            {"name": "borg", "label": "Borgsom (€)", "type": "number"},
            {"name": "start_datum", "label": "Startdatum huur", "type": "date"},
            {"name": "duur_maanden", "label": "Duur contract (maanden)", "type": "number", "default": "12"},
        ],
        "template_text": """HUUROVEREENKOMST

Tussen:
{verhuurder_naam}
{verhuurder_adres}
(hierna te noemen: "Verhuurder")

En:
{huurder_naam}
{huurder_adres}
(hierna te noemen: "Huurder")

Is overeengekomen het volgende:

Artikel 1 - Huurobject
Verhuurder verhuurt aan Huurder: {huurobject}

Artikel 2 - Huurprijs
De maandelijkse huurprijs bedraagt: € {huurprijs}
De huurprijs is verschuldigd voor de eerste dag van elke maand.

Artikel 3 - Borgsom
Huurder betaalt bij ondertekening een borgsom van: € {borg}
De borgsom wordt terugbetaald binnen 30 dagen na beëindiging van de huurovereenkomst, onder aftrek van eventuele schade.

Artikel 4 - Duur
De huurovereenkomst gaat in op: {start_datum}
De huurovereenkomst wordt aangegaan voor de duur van: {duur_maanden} maanden

Artikel 5 - Onderhoud
Verhuurder is verantwoordelijk voor groot onderhoud aan het gehuurde.
Huurder is verantwoordelijk voor klein onderhoud en dagelijks onderhoud.

Artikel 6 - Opzegging
De huurovereenkomst kan worden opgezegd met inachtneming van de wettelijke opzegtermijn.

Artikel 7 - Toepasselijk recht
Op deze overeenkomst is Nederlands recht van toepassing.

Aldus overeengekomen en in tweevoud ondertekend.

Verhuurder: ___________________          Huurder: ___________________
{verhuurder_naam}                          {huurder_naam}"""
    },
    
    "arbeidsovereenkomst": {
        "id": "arbeidsovereenkomst",
        "name": "Arbeidsovereenkomst",
        "category": "Arbeidsrecht",
        "description": "Standaard arbeidsovereenkomst voor onbepaalde tijd",
        "fields": [
            {"name": "werkgever_naam", "label": "Naam werkgever", "type": "text"},
            {"name": "werkgever_adres", "label": "Adres werkgever", "type": "text"},
            {"name": "werknemer_naam", "label": "Naam werknemer", "type": "text"},
            {"name": "werknemer_adres", "label": "Adres werknemer", "type": "text"},
            {"name": "functie", "label": "Functie", "type": "text"},
            {"name": "salaris", "label": "Maandelijks salaris (€)", "type": "number"},
            {"name": "uren_per_week", "label": "Uren per week", "type": "number", "default": "40"},
            {"name": "start_datum", "label": "Startdatum", "type": "date"},
            {"name": "proeftijd_maanden", "label": "Proeftijd (maanden)", "type": "number", "default": "2"},
        ],
        "template_text": """ARBEIDSOVEREENKOMST

Tussen:
{werkgever_naam}
{werkgever_adres}
(hierna te noemen: "Werkgever")

En:
{werknemer_naam}
{werknemer_adres}
(hierna te noemen: "Werknemer")

Is overeengekomen het volgende:

Artikel 1 - Functie
Werknemer wordt aangesteld in de functie van: {functie}

Artikel 2 - Duur
De arbeidsovereenkomst gaat in op: {start_datum}
De arbeidsovereenkomst wordt aangegaan voor onbepaalde tijd.

Artikel 3 - Proeftijd
De eerste {proeftijd_maanden} maanden gelden als proeftijd.

Artikel 4 - Werktijd
De werktijd bedraagt: {uren_per_week} uur per week

Artikel 5 - Salaris
Het bruto maandsalaris bedraagt: € {salaris}
Het salaris wordt maandelijks achteraf betaald.

Artikel 6 - Vakantiedagen
Werknemer heeft recht op 4x de weekwerktijd aan vakantiedagen per jaar.

Artikel 7 - Pensioen
Werknemer neemt deel aan het pensioenfonds van Werkgever.

Artikel 8 - Concurrentiebeding
Na beëindiging van de arbeidsovereenkomst mag Werknemer gedurende 1 jaar geen concurrentiebedrijf bezoeken.

Artikel 9 - Toepasselijk recht
Op deze overeenkomst is Nederlands recht van toepassing.

Aldus overeengekomen en in tweevoud ondertekend.

Werkgever: ___________________          Werknemer: ___________________
{werkgever_naam}                          {werknemer_naam}"""
    },
    
    "adviesbrief": {
        "id": "adviesbrief",
        "name": "Juridische Adviesbrief",
        "category": "Algemeen",
        "description": "Professionele juridische adviesbrief",
        "fields": [
            {"name": "advocaat_naam", "label": "Naam advocaat", "type": "text"},
            {"name": "advocaat_kantoor", "label": "Naam advocatenkantoor", "type": "text"},
            {"name": "client_naam", "label": "Naam cliënt", "type": "text"},
            {"name": "client_adres", "label": "Adres cliënt", "type": "text"},
            {"name": "datum", "label": "Datum", "type": "date"},
            {"name": "dossier_nummer", "label": "Dossiernummer", "type": "text"},
            {"name": "onderwerp", "label": "Onderwerp", "type": "text"},
            {"name": "feitelijk_kader", "label": "Feitelijk kader", "type": "textarea"},
            {"name": "juridische_analyse", "label": "Juridische analyse", "type": "textarea"},
            {"name": "conclusie", "label": "Conclusie/Advies", "type": "textarea"},
        ],
        "template_text": """{advocaat_kantoor}
{advocaat_naam}

{client_naam}
{client_adres}

{datum}

Dossiernummer: {dossier_nummer}

Betreft: {onderwerp}

Geachte {client_naam},

Naar aanleiding van ons gesprek en het door u verstrekte materiaal breng ik hierbij mijn juridische advies uit.

1. FEITELIJK KADER

{feitelijk_kader}

2. JURIDISCHE ANALYSE

{juridische_analyse}

3. CONCLUSIE EN ADVIES

{conclusie}

Mocht u naar aanleiding van dit advies nog vragen hebben, dan verneem ik dat graag.

Met vriendelijke groet,

{advocaat_naam}
{advocaat_kantoor}"""
    },
    
    "dagvaarding": {
        "id": "dagvaarding",
        "name": "Dagvaarding",
        "category": "Procesrecht",
        "description": "Dagvaarding voor de rechtbank",
        "fields": [
            {"name": "eiser_naam", "label": "Naam eiser", "type": "text"},
            {"name": "eiser_adres", "label": "Adres eiser", "type": "text"},
            {"name": "gedaagde_naam", "label": "Naam gedaagde", "type": "text"},
            {"name": "gedaagde_adres", "label": "Adres gedaagde", "type": "text"},
            {"name": "rechtbank", "label": "Rechtbank", "type": "text", "default": "Rechtbank Amsterdam"},
            {"name": "datum", "label": "Datum", "type": "date"},
            {"name": "vordering", "label": "Vordering", "type": "textarea"},
            {"name": "feitelijk_kader", "label": "Feitelijke grondslag", "type": "textarea"},
            {"name": "juridische_grondslag", "label": "Juridische grondslag", "type": "textarea"},
        ],
        "template_text": """DAGVAARDING

Aan: {gedaagde_naam}
{gedaagde_adres}

Namens: {eiser_naam}
{eiser_adres}

Te verschijnen voor: {rechtbank}
Datum: {datum}

1. PARTIJEN

Eiser: {eiser_naam}
Gedaagde: {gedaagde_naam}

2. VORDERING

Eiser vordert bij vonnis, uitvoerbaar bij voorraad:

{vordering}

3. FEITELIJKE GRONDSLAG

{feitelijk_kader}

4. JURIDISCHE GRONDSLAG

{juridische_grondslag}

5. BEWIJS

Eiser beroept zich op alle wettelijke bewijsmiddelen.

6. PROCESKOSTEN

Eiser verzoekt gedaagde te veroordelen in de proceskosten.

Aldus gedaan en betekend.

De advocaat van eiser,

___________________"""
    }
}

# --- Document Drafter Endpoints ---

@app.get("/api/templates")
async def list_templates(
    category: Optional[str] = None,
    api_key: str = Depends(verify_api_key)
):
    """Haal alle templates op"""
    if category:
        templates = [t for t in DOCUMENT_TEMPLATES.values() if t["category"] == category]
    else:
        templates = list(DOCUMENT_TEMPLATES.values())
    
    return {
        "templates": templates,
        "total": len(templates),
        "categories": list(set(t["category"] for t in DOCUMENT_TEMPLATES.values()))
    }

@app.get("/api/templates/{template_id}")
async def get_template(
    template_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Haal template details op"""
    if template_id not in DOCUMENT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Template niet gevonden")
    
    return DOCUMENT_TEMPLATES[template_id]

@app.post("/api/templates/generate", response_model=DocumentGenerateResponse)
async def generate_document(
    request: DocumentGenerateRequest,
    api_key: str = Depends(verify_api_key)
):
    """Genereer document van template"""
    if request.template_id not in DOCUMENT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Template niet gevonden")
    
    template = DOCUMENT_TEMPLATES[request.template_id]
    
    # Haal dossier gegevens op als dossier_id is opgegeven
    dossier_data = {}
    if request.dossier_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dossiers WHERE id = ?", (request.dossier_id,))
        dossier = cursor.fetchone()
        if dossier:
            dossier_data = {
                "client_naam": dossier["client"] or "",
                "dossier_nummer": dossier["id"][:8],
            }
        conn.close()
    
    # Haal analyse gegevens op als analysis_id is opgegeven
    analysis_data = {}
    if request.analysis_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analyses WHERE id = ?", (request.analysis_id,))
        analysis = cursor.fetchone()
        if analysis:
            analysis_data = {
                "juridische_analyse": analysis["summary"] or "",
                "conclusie": analysis["overall_advice"] or "",
            }
        conn.close()
    
    # Combineer alle data
    all_fields = {**dossier_data, **analysis_data, **request.custom_fields}
    
    # Vervang placeholders in template
    content = template["template_text"]
    for key, value in all_fields.items():
        content = content.replace(f"{{{key}}}", str(value))
    
    # Genereer document ID
    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    
    # Sla op in database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO documents (id, template_id, dossier_id, content, title, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (document_id, request.template_id, request.dossier_id, content, template["name"], datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    logger.info(f"Document generated: {document_id}")
    
    return DocumentGenerateResponse(
        document_id=document_id,
        content=content,
        title=template["name"],
        created_at=datetime.now().isoformat()
    )

@app.get("/api/documents/{doc_id}")
async def get_document(
    doc_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Haal gegenereerd document op"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    conn.close()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")
    
    return dict(doc)

@app.post("/api/documents/{doc_id}/export")
async def export_document(
    doc_id: str,
    format: str = "docx",
    api_key: str = Depends(verify_api_key)
):
    """Exporteer document als Word of PDF"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    conn.close()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")
    
    content = doc["content"]
    title = doc["title"]
    
    if format == "docx":
        # Genereer Word document
        from docx import Document
        from docx.shared import Pt, Inches
        from io import BytesIO
        
        docx = Document()
        docx.add_heading(title, 0)
        
        # Voeg content toe met opmaak
        paragraphs = content.split("\n\n")
        for para in paragraphs:
            if para.strip():
                docx.add_paragraph(para.strip())
        
        # Sla op in buffer
        buffer = BytesIO()
        docx.save(buffer)
        buffer.seek(0)
        
        return JSONResponse(
            content={"message": "Document geëxporteerd als Word", "size": len(buffer.getvalue())},
            headers={"Content-Disposition": f"attachment; filename={title}.docx"}
        )
    
    elif format == "pdf":
        # Genereer PDF
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
        
        buffer = BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        
        story = []
        story.append(Paragraph(title, styles['Title']))
        story.append(Spacer(1, 12))
        
        paragraphs = content.split("\n\n")
        for para in paragraphs:
            if para.strip():
                story.append(Paragraph(para.strip(), styles['Normal']))
                story.append(Spacer(1, 6))
        
        pdf.build(story)
        buffer.seek(0)
        
        return JSONResponse(
            content={"message": "Document geëxporteerd als PDF", "size": len(buffer.getvalue())},
            headers={"Content-Disposition": f"attachment; filename={title}.pdf"}
        )
    
    else:
        raise HTTPException(status_code=400, detail="Ongeldig formaat. Gebruik 'docx' of 'pdf'")

@app.get("/api/documents")
async def list_documents(
    dossier_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    api_key: str = Depends(verify_api_key)
):
    """Haal alle gegenereerde documenten op"""
    conn = get_db()
    cursor = conn.cursor()
    
    if dossier_id:
        cursor.execute(
            "SELECT * FROM documents WHERE dossier_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (dossier_id, limit, offset)
        )
    else:
        cursor.execute(
            "SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
    
    documents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"documents": documents, "total": len(documents)}

# --- Start Server ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
