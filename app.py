from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional, Literal
import shutil
import os
import uuid
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="LegalLens Intelligence API",
    description="AI-powered legal analysis for professionals",
    version="4.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
VALID_API_KEYS = os.getenv("VALID_API_KEYS", "demo-key,test-key").split(",")

# --- Models ---
class RiskItem(BaseModel):
    clause_type: str
    severity: str
    description: str
    recommendation: str
    clause_quote: str = ""
    legal_reference: str = ""  # NIEUW: wetsartikel

class DueDiligenceFinding(BaseModel):
    category: str  # Juridisch, Financieel, Operationeel, Commercieel
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
    # NIEUW: Advocaat features
    action_plan: dict = {}
    negotiation_strategy: dict = {}
    due_diligence_findings: List[DueDiligenceFinding] = []
    time_saved_hours: float = 0

class TextAnalysisRequest(BaseModel):
    text: str
    mode: Literal["standard", "advocaat"] = "standard"
    analysis_type: Literal["contract", "due_diligence", "both"] = "contract"

# --- PROFESSIONELE AI ANALYZER ---
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
    
    async def _analyze_with_openai(self, text: str, mode: str, analysis_type: str) -> dict:
        """Echte AI analyse met OpenAI"""
        import requests
        
        # System prompt verschilt per mode
        if mode == "advocaat":
            system_prompt = """Je bent een ervaren Nederlandse advocaat met 20 jaar praktijkervaring.
Je analyseert documenten grondig, citeert specifieke wetsartikelen en jurisprudentie,
en geeft strategisch advies op professioneel niveau.

BELANGRIJKE REGELS:
1. Geef ALLEEN een JSON response, geen andere tekst
2. Gebruik juridisch Nederlands en Latijnse termen waar passend
3. Citeer SPECIFIEKE wetsartikelen (BW, Sr, etc.)
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

        # User prompt verschilt per analysis_type
        if analysis_type == "due_diligence":
            user_prompt = self._build_due_diligence_prompt(text)
        elif analysis_type == "both":
            user_prompt = self._build_combined_prompt(text)
        else:
            user_prompt = self._build_contract_prompt(text)

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
            
            # Voeg tijd besparing toe
            word_count = len(text.split())
            parsed["time_saved_hours"] = round(word_count / 500 * 0.5, 1)
            
            return parsed
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            return await self._analyze_with_huggingface(text, mode, analysis_type)
    
    def _build_contract_prompt(self, text: str) -> str:
        return f"""Analyseer het volgende juridische document grondig:

=== DOCUMENT ===
{text[:8000]}
=== EINDE DOCUMENT ===

Geef een JSON response met deze EXACTE structuur:

{{
  "summary": "Gedetailleerde samenvatting van 3-5 zinnen",
  "contract_type": "Type contract",
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

    def _build_due_diligence_prompt(self, text: str) -> str:
        return f"""Voer een grondige DUE DILIGENCE analyse uit van het volgende document:

=== DOCUMENT ===
{text[:8000]}
=== EINDE DOCUMENT ===

Geef een JSON response met deze EXACTE structuur:

{{
  "summary": "Executive summary van de due diligence bevindingen",
  "contract_type": "Type document/transactie",
  "parties_involved": ["Partij 1", "Partij 2"],
  "key_dates": {{"critical_deadline": "YYYY-MM-DD", "other": "beschrijving"}},
  "risks": [
    {{
      "clause_type": "Risico categorie",
      "severity": "Low/Medium/High/Critical",
      "description": "Beschrijving",
      "recommendation": "Advies",
      "clause_quote": "Citaat",
      "legal_reference": "Wetsartikel"
    }}
  ],
  "overall_advice": "Algemeen advies",
  "sentiment_score": 0.0-1.0,
  "due_diligence_findings": [
    {{
      "category": "Juridisch/Financieel/Operationeel/Commercieel",
      "severity": "Low/Medium/High/Critical",
      "title": "Korte titel",
      "description": "Gedetailleerde beschrijving",
      "recommendation": "Concrete aanbeveling",
      "financial_impact": "Geschatte financiële impact (bijv: €50.000)",
      "legal_reference": "Relevant wetsartikel"
    }}
  ],
  "action_plan": {{
    "direct": ["Directe acties"],
    "short_term": ["Korte termijn acties"],
    "long_term": ["Lange termijn acties"]
  }},
  "negotiation_strategy": {{
    "your_position": "Positie",
    "counterparty_position": "Positie",
    "arguments": ["Argumenten"],
    "alternatives": ["Alternatieven"],
    "fallback": "Fallback"
  }}
}}

BELANGRIJK: 
- Identificeer ALLE risico's (juridisch, financieel, operationeel, commercieel)
- Kwantificeer financiële impact waar mogelijk
- Geef ALLEEN JSON"""

    def _build_combined_prompt(self, text: str) -> str:
        return self._build_due_diligence_prompt(text)
    
    async def _analyze_with_huggingface(self, text: str, mode: str, analysis_type: str) -> dict:
        """Fallback met HuggingFace"""
        import requests
        
        API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct"
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        
        prompt = f"""Analyseer dit document: {text[:4000]}

Geef JSON met: summary, contract_type, parties_involved, key_dates, risks (met clause_type, severity, description, recommendation, clause_quote, legal_reference), overall_advice, sentiment_score, action_plan (met direct, short_term, long_term arrays), negotiation_strategy (met your_position, counterparty_position, arguments, alternatives, fallback), due_diligence_findings (array met category, severity, title, description, recommendation, financial_impact, legal_reference)"""

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
    return {"status": "healthy", "provider": AI_PROVIDER, "version": "4.0.0"}

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
