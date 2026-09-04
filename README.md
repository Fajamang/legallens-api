---
title: LegalLens API
emoji: 🔍
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
---

# LegalLens - AI Contract Analysis API

AI-powered contract analysis and risk extraction.

## Features
- 📝 Text analysis
- 📄 PDF/TXT file upload
- 🤖 Multiple AI providers (HuggingFace, OpenAI, Qwen)
- 🔒 API key protection (optional)

## API Endpoints

### `POST /api/analyze-text`
Analyze text directly.

**Parameters:**
- `text` (string): Contract text to analyze

### `POST /api/analyze-file`
Upload and analyze a file.

**Parameters:**
- `file` (file): PDF or TXT file

### `GET /health`
Health check endpoint.

## Configuration

Set these environment variables in your Hugging Face Space settings:

- `AI_PROVIDER`: "huggingface" (free), "openai", or "qwen"
- `HF_API_TOKEN`: Hugging Face API token (for free tier)
- `OPENAI_API_KEY`: OpenAI API key (for GPT-4)
- `QWEN_API_KEY`: Qwen API key (for Alibaba Cloud)
- `VALID_API_KEYS`: Comma-separated list of API keys (optional)

## Example Usage

```bash
# Analyze text
curl -X POST https://your-space.hf.space/api/analyze-text \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "text=Your contract text here..."

# Analyze file
curl -X POST https://your-space.hf.space/api/analyze-file \
  -F "file=@contract.pdf"