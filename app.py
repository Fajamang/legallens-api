from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional
import shutil
import os
import uuid
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="LegalLens Intelligence API",
    description="AI-powered contract analysis and risk extraction.",
    version="3.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")  # ✅ Nu standaard OpenAI
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
    clause_quote: str = ""  # ✅ NIEUW: citaat uit het document

class AnalysisResult(BaseModel):
    document_id: str
    summary: str
    parties_involved: List[str]
    key_dates: dict
    risks: List[RiskItem]
    overall_advice: str  # ✅ NIEUW: algemeen advies
    sentiment_score: float
    contract_type: str = ""  # ✅ NIEUW: type contract

class TextAnalysisRequest(BaseModel):
    text: str

# --- PROFESSIONELE AI ANALYZER ---
class AIAnalyzer:
    def __init__(self):
        self.provider = AI_PROVIDER
    
    async def analyze_text(self, text: str) -> dict:
        if self.provider == "openai":
            return await self._analyze_with_openai(text)
        elif self.provider == "qwen":
            return await self._analyze_with_qwen(text)
        elif self.provider == "huggingface":
            return await self._analyze_with_huggingface(text)
        else:
            return self._generate_mock_response(text)
    
    async def _analyze_with_openai(self, text: str) -> dict:
        """✅ ECHTE AI ANALYSE met OpenAI GPT-4o-mini"""
        import requests
        
        # Professionele system prompt voor juridische analyse
        system_prompt = """Je bent een ervaren Nederlandse jurist gespecialiseerd in contractanalyse. 
Je analyseert documenten grondig en geeft concrete, bruikbare adviezen.

BELANGRIJKE REGELS:
1. Geef ALLEEN een JSON response, geen andere tekst
2. Baseer ALLES op de feitelijke inhoud van het document
3. Noem concrete namen, bedragen en data uit het document
4. Geef bij elk risico een citaat uit het document
5. Wees specifiek in je adviezen - geen generieke tekst
6. Als er geen risico's zijn, zeg dat dan expliciet"""

        user_prompt = f"""Analyseer het volgende juridische document grondig:

=== DOCUMENT ===
{text[:8000]}
=== EINDE DOCUMENT ===

Geef een JSON response met deze EXACTE structuur:

{{
  "summary": "Gedetailleerde samenvatting van 3-5 zinnen over de kern van dit contract",
  "contract_type": "Type contract (bijv: Huurovereenkomst, Arbeidsovereenkomst, Koopovereenkomst)",
  "parties_involved": ["Volledige naam partij 1 zoals in document", "Volledige naam partij 2"],
  "key_dates": {{
    "start_date": "YYYY-MM-DD of 'niet gevonden'",
    "end_date": "YYYY-MM-DD of 'niet gevonden'",
    "andere_belangrijke_data": "beschrijving"
  }},
  "risks": [
    {{
      "clause_type": "Type clausule (bijv: Boeteclausule, Opzegtermijn, Aansprakelijkheid)",
      "severity": "Low/Medium/High/Critical",
      "description": "Specifieke beschrijving van het risico met concrete details",
      "recommendation": "Concreet advies wat de lezer moet doen",
      "clause_quote": "Letterlijk citaat uit het document dat dit risico toont"
    }}
  ],
  "overall_advice": "Algemeen advies in 2-3 zinnen over dit contract",
  "sentiment_score": 0.0-1.0 (waar 0.0 = zeer ongunstig, 1.0 = zeer gunstig voor de lezer)
}}

BELANGRIJK: 
- Geef ALLEEN de JSON, geen andere tekst
- Gebruik ALLEEN informatie uit het document
- Als je iets niet weet, gebruik "niet gevonden"
- Minimaal 1 risico als er iets ongunstigs staat
- Maximaal 5 risico's (de belangrijkste)"""

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
            "max_tokens": 2000,
            "response_format": {"type": "json_object"}  # ✅ Forceer JSON!
        }
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=90
            )
            response.raise_for_status()
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            
            # Valideer dat het een echte analyse is
            if "Partij A" in str(parsed.get("parties_involved", [])):
                raise ValueError("OpenAI gaf mock data terug")
            
            return parsed
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            # Fallback naar HuggingFace als OpenAI faalt
            return await self._analyze_with_huggingface(text)
    
    async def _analyze_with_huggingface(self, text: str) -> dict:
        """Fallback met HuggingFace"""
        import requests
        
        API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct"
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        
        prompt = f"""Je bent een jurist. Analyseer dit document en geef ALLEEN JSON:

Document: {text[:4000]}

JSON:
{{"summary": "...", "contract_type": "...", "parties_involved": ["...", "..."], "key_dates": {{"start_date": "..."}}, "risks": [{{"clause_type": "...", "severity": "High", "description": "...", "recommendation": "...", "clause_quote": "..."}}], "overall_advice": "...", "sentiment_score": 0.6}}"""

        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 1500, "return_full_text": False}
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
                    return json.loads(generated_text[json_start:json_end])
            except:
                pass
        except Exception as e:
            print(f"HuggingFace error: {e}")
        
        return self._generate_mock_response(text)
    
    async def _analyze_with_qwen(self, text: str) -> dict:
        """Qwen als alternatief"""
        import requests
        
        headers = {
            "Authorization": f"Bearer {QWEN_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "qwen-plus",
            "input": {
                "messages": [
                    {"role": "system", "content": "Je bent een jurist. Geef ALLEEN JSON."},
                    {"role": "user", "content": f"Analyseer:\n\n{text[:4000]}"}
                ]
            },
            "parameters": {"temperature": 0.3, "max_tokens": 2000}
        }
        
        try:
            response = requests.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                headers=headers,
                json=payload,
                timeout=90
            )
            response.raise_for_status()
            result = response.json()
            return json.loads(result["output"]["text"])
        except Exception as e:
            print(f"Qwen error: {e}")
            return await self._analyze_with_huggingface(text)
    
    def _generate_mock_response(self, text: str) -> dict:
        """Alleen als laatste redmiddel"""
        return {
            "summary": f"Analyse van {len(text)} tekens. Upgrade naar OpenAI voor echte analyse.",
            "contract_type": "Onbekend",
            "parties_involved": ["Partij A", "Partij B"],
            "key_dates": {"start_date": "niet gevonden"},
            "risks": [],
            "overall_advice": "Gebruik een echte AI API voor gedetailleerde analyse.",
            "sentiment_score": 0.5
        }

analyzer = AIAnalyzer()

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key and api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key or "public"

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {"status": "healthy", "provider": AI_PROVIDER, "version": "3.0.0"}

@app.post("/api/analyze-text", response_model=AnalysisResult)
async def analyze_text(
    request: TextAnalysisRequest,
    api_key: str = Depends(verify_api_key)
):
    text = request.text
    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Text too short (min 50 characters)")
    
    try:
        result = await analyzer.analyze_text(text)
        return AnalysisResult(document_id=str(uuid.uuid4()), **result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/analyze-file", response_model=AnalysisResult)
async def analyze_file(
    file: UploadFile = File(...),
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
        
        result = await analyzer.analyze_text(text)
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
