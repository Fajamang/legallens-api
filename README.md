# ⚖️ LegalLens Pro

**AI-Powered Legal Analysis Platform for Dutch Legal Professionals**

[![Version](https://img.shields.io/badge/version-9.0.0-blue)](https://github.com/Fajamang/legallens-api)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)
[![Render](https://img.shields.io/badge/deployed-Render-430098)](https://render.com)

---

## 🎯 Wat is LegalLens Pro?

LegalLens Pro is een **professioneel AI-platform** speciaal ontwikkeld voor de Nederlandse juridische markt. Het combineert geavanceerde AI (GPT-4o-mini) met live wetgeving en jurisprudentie om advocaten, juristen en bedrijven te helpen bij:

-  **Contractanalyse** in seconden
- ️ **Due Diligence** automatisering
- 📋 **Risicodetectie** met concrete adviezen
- 📚 **Live wettekst** opzoeken (wetten.overheid.nl)
- ️ **Jurisprudentie** matching (rechtspraak.nl)
- 💼 **Onderhandelingsstrategieën** genereren

> 💡 **Vergelijkbaar met LegalMind (€120/maand), maar dan voor €87/maand**

---

##  Features

### 🎨 Professionele Dashboard UI
- Modern dashboard met real-time statistieken
- Sidebar navigatie (LegalMind-achtig design)
- Dossiers management systeem
- Analyse geschiedenis met zoekfunctie
- Snelle acties knoppen

### 📁 Dossier Management
- Dossiers aanmaken met klantgegevens
- Bestanden uploaden (PDF, TXT, DOCX)
- Meerdere analyses per dossier
- Automatische koppeling bestanden ↔ analyses
- Persistent storage via SQLite

### 🔍 AI Analyse Engine
- **12 rechtsgebieden**: Familierecht, Huurrecht, Arbeidsrecht, Strafrecht, etc.
- **2 modi**: Standaard & Advocaat Mode
- **Risicodetectie** met severity levels (Low/Medium/High/Critical)
- **Citaat extractie** uit documenten
- **Wetsartikel referenties** (BW, Sr, Awb)
- **Strategisch actieplan** (Direct/Korte/Lange termijn)
- **Onderhandelingsstrategie** met argumenten
- **Sentiment analysis** van contracten

###  Smart Legal Reference Sidebar
- Klik op wetsartikel → zijpaneel opent
- **Wettekst** uit database of live (Tavily API)
- **AI Juridisch Commentaar** (GPT-4o-mini)
- **Gerelateerde artikelen** (klikbaar)
- **Wijzigingsgeschiedenis** (timeline)
- **Jurisprudentie** met ECLI nummers

###  Analyse Geschiedenis
- Alle analyses worden bewaard (SQLite)
- Filter op dossier
- Details modal met volledige analyse
- Afdrukken functionaliteit
- Tijdbesparing tracking

### 🔒 Veiligheid & Privacy
- API key authenticatie
- CORS protection
- GDPR compliant
- EU-hosting (Render Frankfurt)
- Geen data-opslag na analyse (optioneel)

---

##  Live Demo

**Bekijk de live applicatie:**
👉 [https://legallens-api-a8ds.onrender.com](https://legallens-api-a8ds.onrender.com)

**API Documentatie (Swagger):**
👉 [https://legallens-api-a8ds.onrender.com/api/docs](https://legallens-api-a8ds.onrender.com/api/docs)

---

## ️ Tech Stack

### Backend
- **FastAPI** 0.115 - Modern Python web framework
- **Python** 3.11+ - Programmeertaal
- **SQLite** - Persistent database
- **OpenAI GPT-4o-mini** - AI analyse engine
- **Tavily API** - Live web search (wetten & jurisprudentie)
- **PyPDF2** - PDF parsing
- **Uvicorn** - ASGI server

### Frontend
- **Vanilla HTML/CSS/JS** - Geen framework dependencies
- **Responsive design** - Werkt op desktop, tablet, mobiel
- **Modern UI** - CSS variables, flexbox, grid

### Deployment
- **GitHub** - Version control
- **Render** - Cloud hosting (Frankfurt)
- **Docker** - Containerization

---

## 📦 Installatie & Setup

### Vereisten
- Python 3.11+
- OpenAI API key
- Tavily API key (optioneel, voor live search)
- Hugging Face token (optioneel, fallback)

### Lokaal draaien
