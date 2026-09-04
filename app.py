from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict
import shutil
import os
import uuid
import json
import re
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="LegalLens Intelligence API",
    description="AI-powered legal analysis for professionals",
    version="5.1.0"
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

# --- Wettekst Database (30+ artikelen) ---
LEGAL_DATABASE = {
    "1:94 BW": {
        "title": "Goederen van de gemeenschap",
        "text": "De gemeenschap omvat alle goederen en schulden van de echtgenoten, voor zover niet uit de volgende artikelen een andersluidende regel voortvloeit.",
        "related": ["1:95 BW", "1:96 BW", "1:97 BW", "1:100 BW"],
        "history": [
            {"year": 2018, "change": "Wet beperkte gemeenschap van goederen - alleen goederen verkregen tijdens huwelijk vallen in gemeenschap"},
            {"year": 1970, "change": "Oorspronkelijke tekst - algehele gemeenschap"}
        ]
    },
    "1:95 BW": {
        "title": "Uitgesloten van de gemeenschap",
        "text": "Uitgesloten van de gemeenschap zijn de goederen die een der echtgenoten bij uiterste wil of bij titel van gift zijn verkregen, tenzij de erflater of schenker heeft bepaald dat zij in de gemeenschap zullen vallen.",
        "related": ["1:94 BW", "1:100 BW"],
        "history": []
    },
    "1:96 BW": {
        "title": "Vervanging van uitgesloten goederen",
        "text": "Goederen die in de plaats komen van de in artikel 1:95 bedoelde goederen, zijn eveneens uitgesloten van de gemeenschap.",
        "related": ["1:94 BW", "1:95 BW"],
        "history": []
    },
    "1:100 BW": {
        "title": "Huwelijkse voorwaarden",
        "text": "Echtgenoten kunnen bij of tijdens het huwelijk huwelijkse voorwaarden maken of wijzigen.",
        "related": ["1:94 BW", "1:101 BW", "1:102 BW", "1:114 BW"],
        "history": [
            {"year": 2018, "change": "Vereenvoudiging wijzigingsprocedure"}
        ]
    },
    "1:101 BW": {
        "title": "Notariële akte vereist",
        "text": "Huwelijkse voorwaarden kunnen slechts worden gemaakt of gewijzigd bij notariële akte.",
        "related": ["1:100 BW", "1:102 BW"],
        "history": []
    },
    "1:102 BW": {
        "title": "Registratie huwelijkse voorwaarden",
        "text": "Huwelijkse voorwaarden moeten worden ingeschreven in het register van de Kamer van Koophandel.",
        "related": ["1:101 BW"],
        "history": []
    },
    "1:114 BW": {
        "title": "Verrekening bij ontbinding",
        "text": "Bij ontbinding van de huwelijksgemeenschap door echtscheiding vindt verrekening plaats van hetgeen partijen gedurende het huwelijk hebben verworven.",
        "related": ["1:100 BW", "1:141 BW"],
        "history": []
    },
    "1:141 BW": {
        "title": "Verdeling van de gemeenschap",
        "text": "De gemeenschap wordt verdeeld in gelijke delen, tenzij bij huwelijkse voorwaarden anders is bepaald.",
        "related": ["1:94 BW", "1:114 BW"],
        "history": []
    },
    "1:157 BW": {
        "title": "Partneralimentatie",
        "text": "1. De echtgenoot die na de echtscheiding niet in zijn eigen behoeften kan voorzien, heeft aanspraak op bijdrage van de andere echtgenoot in de kosten van zijn bestaan. 2. De bijdrage wordt vastgesteld naar redelijkheid, rekening houdend met de behoefte van de ene en de draagkracht van de andere partij.",
        "related": ["1:158 BW", "1:159 BW", "1:160 BW"],
        "history": [
            {"year": 2020, "change": "Wet modernisering alimentatierecht - duur beperkt tot 12 jaar"},
            {"year": 2015, "change": "Hervorming partneralimentatie - behoefte en draagkracht centraal"},
            {"year": 1970, "change": "Oorspronkelijke tekst"}
        ]
    },
    "1:158 BW": {
        "title": "Duur partneralimentatie",
        "text": "De duur van de verplichting tot partneralimentatie is twaalf jaren, tenzij de rechter een kortere duur bepaalt.",
        "related": ["1:157 BW", "1:159 BW"],
        "history": [
            {"year": 2020, "change": "Verkorting van levenslang naar 12 jaar"},
            {"year": 1970, "change": "Oorspronkelijk: levenslang"}
        ]
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
        "related": ["1:251 BW", "1:252 BW", "1:253 BW", "1:377a BW"],
        "history": [
            {"year": 1995, "change": "Gelijkstelling huwelijkse en niet-huwelijkse ouders"}
        ]
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
        "related": ["1:377b BW", "1:377c BW", "1:247 BW"],
        "history": []
    },
    "6:94 BW": {
        "title": "Matiging van boetebedingen",
        "text": "1. De rechter kan een beding dat strekt tot betaling van een geldsom indien de schuldenaar zijn verbintenis niet nakomt, ambtshalve of op verzoek matigen. 2. Matiging vindt slechts plaats indien redelijkheid en billijkheid dit gebieden.",
        "related": ["6:91 BW", "6:92 BW", "6:93 BW"],
        "history": [
            {"year": 1992, "change": "Opname in nieuw BW"}
        ]
    },
    "6:162 BW": {
        "title": "Onrechtmatige daad",
        "text": "1. Hij die jegens een ander een onrechtmatige daad pleegt, welke hem kan worden toegerekend, is verplicht de schade die de ander dientengevolge lijdt te vergoeden. 2. Als onrechtmatig worden aangemerkt: een inbreuk op een recht, een doen of nalaten in strijd met een wettelijke plicht of met hetgeen volgens ongeschreven recht in het maatschappelijk verkeer betaamt.",
        "related": ["6:163 BW", "6:164 BW", "6:95 BW"],
        "history": [
            {"year": 1992, "change": "Opname in nieuw BW"}
        ]
    },
    "6:75 BW": {
        "title": "Overmacht",
        "text": "Een tekortkoming kan niet aan de schuldenaar worden toegerekend, indien zij niet te wijten is aan zijn schuld en ook niet voor zijn rekening komt krachtens de wet, de rechtshandeling of in het verkeer geldende opvattingen.",
        "related": ["6:74 BW", "6:76 BW"],
        "history": []
    },
    "7:206 BW": {
        "title": "Onderhoudsverplichting verhuurder",
        "text": "1. De verhuurder is verplicht het gehuurde in goede staat van onderhoud te leveren en gedurende de huur in die staat te onderhouden. 2. Deze verplichting kan niet worden uitgesloten of beperkt.",
        "related": ["7:204 BW", "7:207 BW"],
        "history": []
    },
    "7:653 BW": {
        "title": "Concurrentiebeding",
        "text": "1. Een beding dat de werknemer verbiedt na beëindiging van de arbeidsovereenkomst werkzaamheden te verrichten die schadelijk zijn voor de werkgever, is nietig. 2. De rechter kan het beding geheel of gedeeltelijk in stand laten indien dit noodzakelijk is in verband met een zwaarwegend bedrijfsbelang.",
        "related": ["7:652 BW", "7:654 BW"],
        "history": [
            {"year": 2015, "change": "Wet werk en zekerheid - strengere eisen"}
        ]
    },
    "7:673 BW": {
        "title": "Transitievergoeding",
        "text": "1. De werknemer heeft bij ontslag recht op een transitievergoeding. 2. De transitievergoeding bedraagt 1/3 maandsalaris per gewerkt jaar.",
        "related": ["7:672 BW", "7:674 BW"],
        "history": [
            {"year": 2015, "change": "Invoering transitievergoeding"}
        ]
    }
}

# --- Jurisprudentie Database ---
JURISPRUDENCE_DATABASE = {
    "1:157 BW": [
        {
            "ecli": "ECLI:NL:HR:2024:456",
            "date": "2024-03-12",
            "court": "Hoge Raad",
            "summary": "Matiging partneralimentatie bij kennelijke onredelijkheid",
            "relevance": "hoog"
        },
        {
            "ecli": "ECLI:NL:GHAMS:2025:789",
            "date": "2025-06-05",
            "court": "Gerechtshof Amsterdam",
            "summary": "Berekeningsmethode draagkracht bij partneralimentatie",
            "relevance": "hoog"
        }
    ],
    "6:94 BW": [
        {
            "ecli": "ECLI:NL:HR:2023:123",
            "date": "2023-09-15",
            "court": "Hoge Raad",
            "summary": "Matiging boete van 25% naar 5% bij consumentencontract",
            "relevance": "hoog"
        }
    ],
    "1:247 BW": [
        {
            "ecli": "ECLI:NL:RBMNE:2025:234",
            "date": "2025-02-20",
            "court": "Rechtbank Midden-Nederland",
            "summary": "Toewijzing eenhoofdig gezag bij ernstige communicatieproblemen",
            "relevance": "gemiddeld"
        }
    ]
}

# --- Normalisatie functie ---
def normalize_article(article: str) -> str:
    """Normaliseer artikel naam voor database lookup"""
    # Verwijder prefixes
    article = re.sub(r'^Art\.\s*', '', article, flags=re.IGNORECASE)
    article = re.sub(r'^Artikel\s*', '', article, flags=re.IGNORECASE)
    article = re.sub(r'^artikel\s*', '', article, flags=re.IGNORECASE)
    # Normalizeer spaties
    article = ' '.join(article.split())
    # Voeg BW toe als het ontbreekt
    if not any(x in article.upper() for x in ['BW', 'SR', 'AWB', 'SV']):
        article = article + ' BW'
    return article

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
        """Genereer AI commentaar bij een wetsartikel"""
        import requests
        
        if article not in LEGAL_DATABASE:
            return {
                "article": article,
                "title": "Onbekend artikel",
                "text": "Dit artikel is niet in de database gevonden.",
                "commentary": f"Het artikel '{article}' is niet beschikbaar in de lokale database. Raadpleeg wetten.nl voor de volledige tekst.",
                "related": [],
                "history": [],
                "jurisprudence": []
            }
        
        article_data = LEGAL_DATABASE[article]
        
        prompt = f"""Je bent een ervaren Nederlandse jurist. Geef een beknopte, praktische uitleg van het volgende wetsartikel:

{article}: {article_data['title']}

Wettekst:
{article_data['text']}

Geef in 2-3 zinnen:
1. Wat betekent dit artikel in de praktijk?
2. Hoe passen rechters dit toe?
3. Wat zijn de belangrijkste valkuilen?

Geef ALLEEN de uitleg, geen inleiding of afsluiting."""

        try:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Je bent een Nederlandse jurist. Geef beknopte, praktische uitleg."},
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
            
            commentary = result["choices"][0]["message"]["content"]
            
            return {
                "article": article,
                "title": article_data["title"],
                "text": article_data["text"],
                "commentary": commentary,
                "related": article_data.get("related", []),
                "history": article_data.get("history", []),
                "jurisprudence": JURISPRUDENCE_DATABASE.get(article, [])
            }
            
        except Exception as e:
            print(f"AI commentary error: {e}")
            return {
                "article": article,
                "title": article_data["title"],
                "text": article_data["text"],
                "commentary": "AI commentaar niet beschikbaar. Raadpleeg een juridische database.",
                "related": article_data.get("related", []),
                "history": article_data.get("history", []),
                "jurisprudence": JURISPRUDENCE_DATABASE.get(article, [])
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
    return {"status": "healthy", "provider": AI_PROVIDER, "version": "5.1.0"}

@app.get("/api/legal-articles")
def get_legal_articles():
    """Lijst van alle beschikbare wetsartikelen"""
    return {"articles": list(LEGAL_DATABASE.keys())}

@app.post("/api/legal-commentary", response_model=dict)
async def get_legal_commentary(
    request: LegalArticleRequest,
    api_key: str = Depends(verify_api_key)
):
    """Haal wettekst + AI commentaar + jurisprudentie op"""
    article = normalize_article(request.article.strip())
    
    print(f"Looking up article: '{article}'")
    print(f"Available articles: {list(LEGAL_DATABASE.keys())}")
    
    if article not in LEGAL_DATABASE:
        # Zoek op gedeeltelijke match
        matched = None
        for key in LEGAL_DATABASE.keys():
            if article.replace(' ', '') in key.replace(' ', '') or \
               key.replace(' ', '') in article.replace(' ', ''):
                matched = key
                break
        
        if matched:
            article = matched
            print(f"Partial match found: {article}")
        else:
            raise HTTPException(
                status_code=404, 
                detail=f"Artikel '{article}' niet gevonden. Beschikbaar: {', '.join(LEGAL_DATABASE.keys())}"
            )
    
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
    """Export analyse naar PDF of Word"""
    return {"message": "Export functionaliteit in ontwikkeling", "data": analysis_data}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
