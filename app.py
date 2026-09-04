from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Literal
import shutil
import os
import uuid
import json
import re
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="LegalLens Intelligence API",
    description="AI-powered legal analysis with live web search",
    version="6.0.0-Agentic"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
VALID_API_KEYS = os.getenv("VALID_API_KEYS", "demo-key,test-key").split(",")

# --- Models ---
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
    key_dates: dict
    risks: List[RiskItem]
    overall_advice: str
    sentiment_score: float
    action_plan: dict = {}
    negotiation_strategy: dict = {}
    due_diligence_findings: List[DueDiligenceFinding] = []
    time_saved_hours: float = 0

class TextAnalysisRequest(BaseModel):
    text: str
    mode: Literal["standard", "advocaat"] = "standard"
    analysis_type: str = "contract"

class LegalArticleRequest(BaseModel):
    article: str

# --- Helper: Normaliseer artikel ---
def normalize_article(article: str) -> str:
    article = re.sub(r'^Art\.\s*', '', article, flags=re.IGNORECASE)
    article = re.sub(r'^Artikel\s*', '', article, flags=re.IGNORECASE)
    article = ' '.join(article.split())
    if not any(x in article.upper() for x in ['BW', 'SR', 'AWB']):
        article = article + ' BW'
    return article

# --- LIVE SEARCH ENGINE ---
class LiveLegalSearch:
    def __init__(self):
        try:
            from duckduckgo_search import DDGS
            self.ddgs = DDGS()
            self.available = True
        except Exception as e:
            print(f"Search engine init failed: {e}")
            self.available = False

    async def search_bw_text(self, article: str) -> str:
        """Zoek de exacte wettekst op wetten.overheid.nl"""
        if not self.available:
            return "Zoekfunctie tijdelijk niet beschikbaar."
        
        try:
            query = f"Artikel {article} Burgerlijk Wetboek site:wetten.overheid.nl"
            results = self.ddgs.text(query, max_results=1)
            if results:
                return results[0].get('body', 'Tekst niet gevonden.')
            return "Wettekst niet gevonden."
        except Exception as e:
            print(f"BW Search error: {e}")
            return "Fout bij ophalen wettekst."

    async def search_case_law(self, article: str) -> List[dict]:
        """Zoek recente jurisprudentie op rechtspraak.nl"""
        if not self.available:
            return []
        
        try:
            query = f"Artikel {article} BW uitspraak site:rechtspraak.nl"
            results = self.ddgs.text(query, max_results=3)
            
            cases = []
            for r in results:
                cases.append({
                    "title": r.get('title', 'Onbekende zaak'),
                    "url": r.get('href', ''),
                    "snippet": r.get('body', ''),
                    "date": "Recent"
                })
            return cases
        except Exception as e:
            print(f"Case law search error: {e}")
            return []

live_search = LiveLegalSearch()

# --- AI Analyzer ---
class AIAnalyzer:
    def __init__(self):
        self.provider = AI_PROVIDER
    
    async def analyze_text(self, text: str, mode: str = "standard", analysis_type: str = "contract") -> dict:
        if self.provider == "openai":
            return await self._analyze_with_openai(text, mode, analysis_type)
        elif self.provider == "huggingface":
            return await self._analyze_with_huggingface(text, mode, analysis_type)
        else:
            return self._generate_mock_response(text)
    
    async def get_legal_commentary(self, article: str) -> dict:
        """Haal LIVE data op en laat AI de analyse doen"""
        import requests
        
        print(f"🔍 Live searching for: {article}")
        
        # 1. Haal live data op
        bw_text = await live_search.search_bw_text(article)
        case_law = await live_search.search_case_law(article)
        
        # 2. Bouw de prompt voor OpenAI met de LIVE data
        prompt = f"""Je bent een ervaren Nederlandse jurist. 
Ik heb zojuist live de volgende informatie gevonden over **{article}**:

**WETTEKST (van wetten.overheid.nl):**
{bw_text}

**RECENTE JURISPRUDENTIE (van rechtspraak.nl):**
{json.dumps(case_law, indent=2)}

---
OPDRACHT:
Geef op basis van DEZE LIVE DATA een beknopt juridisch commentaar:
1. Wat betekent dit artikel in de praktijk? (2 zinnen)
2. Hoe passen rechters dit toe volgens de gevonden uitspraken? (2 zinnen)
3. Wat zijn de valkuilen? (1 zin)

Geef ALLEEN het commentaar, geen inleiding."""

        try:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Je bent een Nederlandse jurist. Analyseer de live data."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 400
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            commentary = result["choices"][0]["message"]["content"]
            
            return {
                "article": article,
                "title": f"Live analyse: {article}",
                "text": bw_text,
                "commentary": commentary,
                "related": [],
                "history": [{"year": 2026, "change": "Live data opgehaald via wetten.overheid.nl"}],
                "jurisprudence": [
                    {
                        "ecli": c.get('title', 'Zaak'),
                        "date": c.get('date', ''),
                        "court": "Rechtspraak.nl",
                        "summary": c.get('snippet', ''),
                        "relevance": "hoog",
                        "url": c.get('url', '')
                    } for c in case_law
                ]
            }
            
        except Exception as e:
            print(f"AI commentary error: {e}")
            return {
                "article": article,
                "title": "Fout bij AI analyse",
                "text": bw_text,
                "commentary": f"Kon geen AI commentaar genereren. Error: {str(e)}",
                "related": [],
                "history": [],
                "jurisprudence": []
            }
    
    async def _analyze_with_openai(self, text: str, mode: str, analysis_type: str) -> dict:
        import requests
        
        if mode == "advocaat":
            system_prompt = """Je bent een ervaren Nederlandse advocaat met 20 jaar praktijkervaring.
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
            system_prompt = """Je bent een ervaren Nederlandse jurist gespecialiseerd in contractanalyse.
Je analyseert documenten grondig en geeft concrete, bruikbare adviezen.

BELANGRIJKE REGELS:
1. Geef ALLEEN een JSON response, geen andere tekst
2. Baseer ALLES op de feitelijke inhoud van het document
3. Noem concrete namen, bedragen en data uit het document
4. Geef bij elk risico een citaat uit het document
5. Wees specifiek in je adviezen"""

        user_prompt = f"""Analyseer het volgende juridische document:

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

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
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
        
        try:
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
            print(f"OpenAI error: {e}")
            return self._generate_mock_response(text)
    
    async def _analyze_with_huggingface(self, text: str, mode: str, analysis_type: str) -> dict:
        import requests
        
        API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct"
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        
        prompt = f"""Analyseer dit document: {text[:4000]}

Geef JSON met: summary, contract_type, parties_involved, key_dates, risks, overall_advice, sentiment_score, action_plan, negotiation_strategy"""

        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 2000, "return_full_text": False}
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            result = response.json()
            generated_text = result[0]["generated_text"] if isinstance(result, list) else result.get("generated_text", "")
            
            try:
                json_start = generated_text.find("{")
                json_end = generated_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    parsed = json.loads(generated_text[json_start:json_end])
                    parsed["time_saved_hours"] = 2.0
                    return parsed
            except:
                pass
        except Exception as e:
            print(f"HuggingFace error: {e}")
        
        return self._generate_mock_response(text)
    
    def _generate_mock_response(self, text: str) -> dict:
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

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key and api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key or "public"

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("static/index.html")

@app.get("/advocaten", response_class=HTMLResponse)
async def advocaten_page():
    return FileResponse("static/advocaten.html")

@app.get("/health")
def health_check():
    return {"status": "healthy", "provider": AI_PROVIDER, "version": "6.0.0-Agentic"}

@app.get("/api/legal-articles")
def get_legal_articles():
    return {"message": "Live search enabled - no static database needed"}

@app.post("/api/legal-commentary", response_model=dict)
async def get_legal_commentary(
    request: LegalArticleRequest,
    api_key: str = Depends(verify_api_key)
):
    article = normalize_article(request.article.strip())
    print(f"Looking up article: '{article}'")
    
    try:
        result = await analyzer.get_legal_commentary(article)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-text", response_model=AnalysisResult)
async def analyze_text(
    request: TextAnalysisRequest,
    api_key: str = Depends(verify_api_key)
):
    text = request.text
    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Text too short (min 50 characters)")
    
    try:
        result = await analyzer.analyze_text(text, request.mode, request.analysis_type)
        return AnalysisResult(document_id=str(uuid.uuid4()), **result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/analyze-file", response_model=AnalysisResult)
async def analyze_file(
    file: UploadFile = File(...),
    mode: str = Form("standard"),
    analysis_type: str = Form("contract"),
    api_key: str = Depends(verify_api_key)
):
    if not file.filename.endswith(('.pdf', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files supported")
    
    file_location = f"temp_{uuid.uuid4()}_{file.filename}"
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    
    try:
        text = ""
        if file.filename.endswith('.txt'):
            with open(file_location, 'r', encoding='utf-8') as f:
                text = f.read()
        elif file.filename.endswith('.pdf'):
            try:
                import PyPDF2
                with open(file_location, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            except ImportError:
                raise HTTPException(status_code=500, detail="PDF support not configured")
        else:
            raise HTTPException(status_code=400, detail="File type not supported")
        
        if not text or len(text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Could not extract enough text")
        
        result = await analyzer.analyze_text(text, mode, analysis_type)
        return AnalysisResult(document_id=str(uuid.uuid4()), **result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_location):
            os.remove(file_location)

@app.post("/api/export-report")
async def export_report(
    analysis_data: dict,
    format: str = "pdf",
    api_key: str = Depends(verify_api_key)
):
    return {"message": "Export functionaliteit in ontwikkeling", "data": analysis_data}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
