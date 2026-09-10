"""
LegalLens Pro API v9.0
Robuuste backend met database, file storage, en alle features
"""

import os
import re
import json
import uuid
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any

import requests
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

DB_PATH = Path("legallens.db")

def init_db():
    """Initialiseer SQLite database"""
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
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

# Initialiseer database bij startup
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

# --- Wettekst Database ---
LEGAL_DATABASE: Dict[str, Dict] = {
    "1:94 BW": {
        "title": "Goederen van de gemeenschap",
        "text": "De gemeenschap omvat alle goederen en schulden van de echtgenoten, voor zover niet uit de volgende artikelen een andersluidende regel voortvloeit.",
        "related": ["1:95 BW", "1:96 BW", "1:100 BW"],
        "history": [{"year": 2018, "change": "Wet beperkte gemeenschap van goederen"}]
    },
    "1:95 BW": {
        "title": "Uitgesloten van de gemeenschap",
        "text": "Uitgesloten van de gemeenschap zijn de goederen die een der echtgenoten bij uiterste wil of bij titel van gift zijn verkregen, tenzij de erflater of schenker heeft bepaald dat zij in de gemeenschap zullen vallen.",
        "related": ["1:94 BW", "1:100 BW"],
        "history": []
    },
    "1:100 BW": {
        "title": "Huwelijkse voorwaarden",
        "text": "Echtgenoten kunnen bij of tijdens het huwelijk huwelijkse voorwaarden maken of wijzigen.",
        "related": ["1:94 BW", "1:101 BW", "1:102 BW"],
        "history": [{"year": 2018, "change": "Vereenvoudiging wijzigingsprocedure"}]
    },
    "1:157 BW": {
        "title": "Partneralimentatie",
        "text": "1. De echtgenoot die na de echtscheiding niet in zijn eigen behoeften kan voorzien, heeft aanspraak op bijdrage van de andere echtgenoot in de kosten van zijn bestaan. 2. De bijdrage wordt vastgesteld naar redelijkheid, rekening houdend met de behoefte van de ene en de draagkracht van de andere partij.",
        "related": ["1:158 BW", "1:159 BW", "1:160 BW"],
        "history": [{"year": 2020, "change": "Wet modernisering alimentatierecht"}]
    },
    "1:158 BW": {
        "title": "Duur partneralimentatie",
        "text": "De duur van de verplichting tot partneralimentatie is twaalf jaren, tenzij de rechter een kortere duur bepaalt.",
        "related": ["1:157 BW", "1:159 BW"],
        "history": [{"year": 2020, "change": "Verkorting van levenslang naar 12 jaar"}]
    },
    "1:159 BW": {
        "title": "Herziening partneralimentatie",
        "text": "Op verzoek van een der partijen kan de rechter de vastgestelde bijdrage wijzigen of geheel of gedeeltelijk opheffen.",
        "related": ["1:157 BW", "1:158 BW"],
        "history": []
    },
    "1:160 BW": {
        "title": "Einde partneralimentatie",
        "text": "De verplichting tot partneralimentatie eindigt door het overlijden van de rechthebbende of de verplichte, door hertrouwen of het aangaan van een geregistreerd partnerschap van de rechthebbende.",
        "related": ["1:157 BW", "1:158 BW"],
        "history": []
    },
    "1:247 BW": {
        "title": "Ouderlijk gezag",
        "text": "1. Ouders zijn verplicht om hun minderjarig kind te verzorgen en op te voeden. 2. Het gezag omvat de verplichting en het recht om de persoon en het vermogen van het kind te verzorgen.",
        "related": ["1:251 BW", "1:252 BW", "1:377a BW"],
        "history": [{"year": 1995, "change": "Gelijkstelling huwelijkse en niet-huwelijkse ouders"}]
    },
    "1:251 BW": {
        "title": "Gezamenlijk gezag",
        "text": "Het gezag over een minderjarig kind wordt uitgeoefend door beide ouders, tenzij het gezag aan één ouder is toegewezen.",
        "related": ["1:247 BW", "1:252 BW"],
        "history": []
    },
    "1:252 BW": {
        "title": "Eenhoofdig gezag",
        "text": "De rechter kan het gezag aan één ouder toewijzen indien het gezamenlijk gezag niet in het belang van het kind is.",
        "related": ["1:247 BW", "1:251 BW"],
        "history": []
    },
    "1:377a BW": {
        "title": "Omgangsrecht",
        "text": "1. De ouder die niet het gezag uitoefent, heeft recht op omgang met het kind. 2. Het kind heeft recht op omgang met de ouder die niet het gezag uitoefent.",
        "related": ["1:247 BW", "1:377b BW"],
        "history": []
    },
    "6:94 BW": {
        "title": "Matiging van boetebedingen",
        "text": "1. De rechter kan een beding dat strekt tot betaling van een geldsom indien de schuldenaar zijn verbintenis niet nakomt, ambtshalve of op verzoek matigen. 2. Matiging vindt slechts plaats indien redelijkheid en billijkheid dit gebieden.",
        "related": ["6:91 BW", "6:92 BW", "6:93 BW"],
        "history": [{"year": 1992, "change": "Opname in nieuw BW"}]
    },
    "6:162 BW": {
        "title": "Onrechtmatige daad",
        "text": "1. Hij die jegens een ander een onrechtmatige daad pleegt, welke hem kan worden toegerekend, is verplicht de schade die de ander dientengevolge lijdt te vergoeden. 2. Als onrechtmatig worden aangemerkt: een inbreuk op een recht, een doen of nalaten in strijd met een wettelijke plicht of met hetgeen volgens ongeschreven recht in het maatschappelijk verkeer betaamt.",
        "related": ["6:163 BW", "6:95 BW"],
        "history": [{"year": 1992, "change": "Opname in nieuw BW"}]
    },
    "6:75 BW": {
        "title": "Overmacht",
        "text": "Een tekortkoming kan niet aan de schuldenaar worden toegerekend, indien zij niet te wijten is aan zijn schuld en ook niet voor zijn rekening komt krachtens de wet, de rechtshandeling of in het verkeer geldende opvattingen.",
        "related": ["6:74 BW", "6:76 BW"],
        "history": []
    },
    "7:204 BW": {
        "title": "Gebreken aan het gehuurde",
        "text": "1. Een gebrek is een staat of eigenschap van het gehuurde die niet in overeenstemming is met de overeenkomst en daardoor de huurder het genot van het gehuurde ontneemt of beperkt. 2. Een gebrek wordt de huurder niet tegengeworpen indien hij het gebrek niet kende en niet behoorde te kennen bij het aangaan van de overeenkomst.",
        "related": ["7:206 BW", "7:207 BW"],
        "history": []
    },
    "7:206 BW": {
        "title": "Onderhoudsverplichting verhuurder",
        "text": "1. De verhuurder is verplicht het gehuurde in goede staat van onderhoud te leveren en gedurende de huur in die staat te onderhouden. 2. Deze verplichting kan niet worden uitgesloten of beperkt.",
        "related": ["7:204 BW", "7:207 BW"],
        "history": []
    },
    "7:207 BW": {
        "title": "Herstel van gebreken",
        "text": "1. Indien het gehuurde gebreken heeft die de verhuurder overeenkomstig artikel 7:206 had moeten verhelpen, kan de huurder de verhuurder schriftelijk in gebreke stellen en een redelijke termijn voor herstel bepalen.",
        "related": ["7:204 BW", "7:206 BW"],
        "history": []
    },
    "7:653 BW": {
        "title": "Concurrentiebeding",
        "text": "1. Een beding dat de werknemer verbiedt na beëindiging van de arbeidsovereenkomst werkzaamheden te verrichten die schadelijk zijn voor de werkgever, is nietig. 2. De rechter kan het beding geheel of gedeeltelijk in stand laten indien dit noodzakelijk is in verband met een zwaarwegend bedrijfsbelang.",
        "related": ["7:652 BW", "7:654 BW"],
        "history": [{"year": 2015, "change": "Wet werk en zekerheid"}]
    },
    "7:673 BW": {
        "title": "Transitievergoeding",
        "text": "1. De werknemer heeft bij ontslag recht op een transitievergoeding. 2. De transitievergoeding bedraagt 1/3 maandsalaris per gewerkt jaar.",
        "related": ["7:672 BW", "7:674 BW"],
        "history": [{"year": 2015, "change": "Invoering transitievergoeding"}]
    }
}

# --- Jurisprudentie Database ---
JURISPRUDENCE_DATABASE: Dict[str, List[Dict]] = {
    "1:157 BW": [
        {"ecli": "ECLI:NL:HR:2024:456", "date": "2024-03-12", "court": "Hoge Raad", "summary": "Matiging partneralimentatie bij kennelijke onredelijkheid", "relevance": "hoog"},
        {"ecli": "ECLI:NL:GHAMS:2025:789", "date": "2025-06-05", "court": "Gerechtshof Amsterdam", "summary": "Berekeningsmethode draagkracht bij partneralimentatie", "relevance": "hoog"}
    ],
    "6:94 BW": [
        {"ecli": "ECLI:NL:HR:2023:123", "date": "2023-09-15", "court": "Hoge Raad", "summary": "Matiging boete van 25% naar 5% bij consumentencontract", "relevance": "hoog"}
    ],
    "1:247 BW": [
        {"ecli": "ECLI:NL:RBMNE:2025:234", "date": "2025-02-20", "court": "Rechtbank Midden-Nederland", "summary": "Toewijzing eenhoofdig gezag bij ernstige communicatieproblemen", "relevance": "gemiddeld"}
    ]
}

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

# --- Live Search Engine ---
class LiveLegalSearch:
    """Zoekmachine voor live wettekst en jurisprudentie"""
    
    def __init__(self):
        self.api_key = TAVILY_API_KEY
        self.available = bool(self.api_key)
        if not self.available:
            logger.warning("Tavily API key niet gevonden - alleen database beschikbaar")

    async def search_bw_text(self, article: str) -> str:
        """Zoek wettekst op via Tavily"""
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
        """Zoek jurisprudentie op via Tavily"""
        if not self.available:
            return []
        
        try:
            headers = {"Content-Type": "application/json", "api-key": self.api_key}
            query = f"Artikel {article} BW uitspraak rechtspraak.nl Hoge Raad"
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
        """Haal wettekst + AI commentaar op"""
        logger.info(f"Looking up article: {article}")
        
        bw_text = await self._get_bw_text(article)
        case_law = await self._get_case_law(article)
        
        db_entry = LEGAL_DATABASE.get(article, {})
        title = db_entry.get("title", f"Artikel {article}")
        related = db_entry.get("related", [])
        history = db_entry.get("history", [])
        
        commentary = await self._generate_commentary(article, title, bw_text)
        
        return {
            "article": article,
            "title": title,
            "text": bw_text,
            "commentary": commentary,
            "related": related,
            "history": history,
            "jurisprudence": case_law
        }
    
    async def _get_bw_text(self, article: str) -> str:
        """Haal wettekst op"""
        if article in LEGAL_DATABASE:
            return LEGAL_DATABASE[article]["text"]
        return await live_search.search_bw_text(article)
    
    async def _get_case_law(self, article: str) -> List[Dict]:
        """Haal jurisprudentie op"""
        if article in JURISPRUDENCE_DATABASE:
            return JURISPRUDENCE_DATABASE[article]
        return await live_search.search_case_law(article)
    
    async def _generate_commentary(self, article: str, title: str, bw_text: str) -> str:
        """Genereer AI commentaar"""
        try:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            prompt = f"""Je bent een ervaren Nederlandse jurist. Geef een beknopte, praktische uitleg van:

**{article}: {title}**

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
    # Check if dossier exists
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM dossiers WHERE id = ?", (dossier_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")
    
    # Save file
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    saved_filename = f"{file_id}{file_ext}"
    file_path = UPLOAD_DIR / saved_filename
    
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Save to database
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
    
    # Save file temporarily
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    temp_path = UPLOAD_DIR / f"temp_{file_id}{file_ext}"
    
    with open(temp_path, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    
    try:
        # Extract text
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
        
        # Analyze
        result = await analyzer.analyze_text(text, mode, analysis_type)
        
        # Save analysis to database
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
        
        # Save file to database if dossier_id provided
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
        # Parse JSON fields
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
    
    # Parse JSON fields
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

@app.get("/api/legal-articles")
def get_legal_articles():
    """Lijst van beschikbare wetsartikelen"""
    return {
        "database_articles": list(LEGAL_DATABASE.keys()),
        "live_search_available": live_search.available
    }

# --- Statistics Endpoint ---

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

# --- Start Server ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
