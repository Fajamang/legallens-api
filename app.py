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

# Load environment variables
load_dotenv()

# --- Configuratie ---
app = FastAPI(
    title="LegalLens Intelligence API",
    description="AI-powered contract analysis and risk extraction.",
    version="2.0.0"
)

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# API Key beveiliging (optioneel)
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Configuratie uit environment variables
AI_PROVIDER = os.getenv("AI_PROVIDER", "huggingface")  # "huggingface", "openai", of "qwen"
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

class AnalysisResult(BaseModel):
    document_id: str
    summary: str
    parties_involved: List[str]
    key_dates: dict
    risks: List[RiskItem]
    sentiment_score: float

# --- AI Providers ---
class AIAnalyzer:
    def __init__(self):
        self.provider = AI_PROVIDER
        
    async def analyze_text(self, text: str) -> dict:
        """Kies de juiste AI provider op basis van configuratie"""
        if self.provider == "huggingface":
            return await self._analyze_with_huggingface(text)
        elif self.provider == "openai":
            return await self._analyze_with_openai(text)
        elif self.provider == "qwen":
            return await self._analyze_with_qwen(text)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    async def _analyze_with_huggingface(self, text: str) -> dict:
        """Gratis analyse met Hugging Face Inference API (Llama 3)"""
        import requests
        
        API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-3B-Instruct"
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        
        prompt = f"""Analyzeer dit juridische document en geef een JSON response:

Document: {text[:4000]}

Geef een JSON met:
- summary: korte samenvatting (max 100 woorden)
- parties_involved: lijst van betrokken partijen
- key_dates: dict met belangrijke data
- risks: lijst van risico's met clause_type, severity (Low/Medium/High/Critical), description, recommendation
- sentiment_score: float tussen 0 en 1

JSON:"""

        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 1000, "return_full_text": False}
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            
            # Parse JSON uit response
            generated_text = result[0]["generated_text"] if isinstance(result, list) else result["generated_text"]
            
            # Probeer JSON te extraheren
            try:
                # Zoek JSON in de response
                json_start = generated_text.find("{")
                json_end = generated_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = generated_text[json_start:json_end]
                    return json.loads(json_str)
            except:
                pass
            
            # Fallback: genereer mock data
            return self._generate_mock_response(text)
            
        except Exception as e:
            print(f"HuggingFace error: {e}")
            return self._generate_mock_response(text)
    
    async def _analyze_with_openai(self, text: str) -> dict:
        """Betaalde analyse met OpenAI GPT-4"""
        import requests
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": "Je bent een juridische AI-assistent. Analyseer documenten en geef ALLEEN een JSON response zonder extra tekst."
                },
                {
                    "role": "user",
                    "content": f"""Analyseer dit juridische document:

{text[:4000]}

Geef een JSON met deze structuur:
{{
  "summary": "korte samenvatting",
  "parties_involved": ["partij1", "partij2"],
  "key_dates": {{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}},
  "risks": [
    {{
      "clause_type": "type clausule",
      "severity": "Low/Medium/High/Critical",
      "description": "beschrijving",
      "recommendation": "advies"
    }}
  ],
  "sentiment_score": 0.5
}}"""
                }
            ],
            "temperature": 0.3,
            "max_tokens": 1500
        }
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            return self._generate_mock_response(text)
    
    async def _analyze_with_qwen(self, text: str) -> dict:
        """Betaalde analyse met Qwen (Alibaba Cloud)"""
        import requests
        
        headers = {
            "Authorization": f"Bearer {QWEN_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "qwen-plus",
            "input": {
                "messages": [
                    {
                        "role": "system",
                        "content": "Je bent een juridische AI-assistent. Geef ALLEEN JSON responses."
                    },
                    {
                        "role": "user",
                        "content": f"Analyseer dit document en geef JSON met summary, parties_involved, key_dates, risks, sentiment_score:\n\n{text[:4000]}"
                    }
                ]
            },
            "parameters": {"temperature": 0.3, "max_tokens": 1500}
        }
        
        try:
            response = requests.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            content = result["output"]["text"]
            return json.loads(content)
            
        except Exception as e:
            print(f"Qwen error: {e}")
            return self._generate_mock_response(text)
    
    def _generate_mock_response(self, text: str) -> dict:
        """Fallback mock response"""
        risks = []
        if "boete" in text.lower():
            risks.append({
                "clause_type": "Boeteclausule",
                "severity": "High",
                "description": "Boeteclausule gedetecteerd",
                "recommendation": "Onderhandel over lagere boete"
            })
        
        return {
            "summary": f"Document analyse van {len(text)} tekens. Dit is een demo response.",
            "parties_involved": ["Partij A", "Partij B"],
            "key_dates": {"start_date": "2026-01-01", "end_date": "2027-01-01"},
            "risks": risks,
            "sentiment_score": 0.6
        }

# Initialize AI analyzer
analyzer = AIAnalyzer()

# --- Dependencies ---
async def verify_api_key(api_key: str = Depends(api_key_header)):
    """Verifieer API key (optioneel voor publieke demo)"""
    if api_key and api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key or "public"

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve de frontend"""
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "provider": AI_PROVIDER,
        "version": "2.0.0"
    }

@app.post("/api/analyze-text", response_model=AnalysisResult)
async def analyze_text(
    text: str,
    api_key: str = Depends(verify_api_key)
):
    """Analyseer tekst direct (geen file upload)"""
    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Text too short (min 50 characters)")
    
    try:
        result = await analyzer.analyze_text(text)
        
        return AnalysisResult(
            document_id=str(uuid.uuid4()),
            **result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/analyze-file", response_model=AnalysisResult)
async def analyze_file(
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key)
):
    """Analyseer een geüpload bestand (PDF/DOCX)"""
    if not file.filename.endswith(('.pdf', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files supported")
    
    # Save file temporarily
    file_location = f"temp_{uuid.uuid4()}_{file.filename}"
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    
    try:
        # Extract text from file
        text = ""
        if file.filename.endswith('.txt'):
            with open(file_location, 'r', encoding='utf-8') as f:
                text = f.read()
        elif file.filename.endswith('.pdf'):
            # PDF parsing (vereist PyPDF2 in requirements.txt)
            try:
                import PyPDF2
                with open(file_location, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "\n".join([page.extract_text() for page in reader.pages])
            except ImportError:
                raise HTTPException(status_code=500, detail="PDF support not configured")
        else:
            raise HTTPException(status_code=400, detail="File type not supported yet")
        
        if not text or len(text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Could not extract enough text from file")
        
        # Analyze extracted text
        result = await analyzer.analyze_text(text)
        
        return AnalysisResult(
            document_id=str(uuid.uuid4()),
            **result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        if os.path.exists(file_location):
            os.remove(file_location)

@app.post("/api/analyze", response_model=AnalysisResult)
async def analyze_contract(
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key)
):
    """Legacy endpoint voor backward compatibility"""
    return await analyze_file(file, api_key)

# --- Start Server ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))  # Hugging Face gebruikt poort 7860
    uvicorn.run(app, host="0.0.0.0", port=port)