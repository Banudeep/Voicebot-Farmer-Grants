# USDA Farmer Voice Assistant

<div align="center">

**A Real-Time AI Voice Agent for Farmers**
_Powered by Azure OpenAI Responses API, Azure Speech Services, and USDA Data_

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](Dockerfile)
[![Azure](https://img.shields.io/badge/Azure-Cloud-0078D4.svg)](https://azure.microsoft.com/)

</div>

---

## Architecture

<img src="images/Farmer-Voicebot.png" alt="Architecture Diagram" width="800"/>

A **low-latency voice assistant** that lets farmers interact with complex USDA services using natural speech. It combines real-time streaming speech processing with a tool-use agent (MCP) — backed by Azure OpenAI's **Responses API** with chain-of-thought reasoning — to perform actual work: filling forms, looking up grants, fetching prices, and more.

The system runs as two services:

| Service                            | Port   | Description                                                        |
| ---------------------------------- | ------ | ------------------------------------------------------------------ |
| **Voice Agent** (Python / aiohttp) | `8080` | WebSocket server orchestrating STT → LLM → TTS pipeline, PDF API   |
| **Next.js UI** (React 19)          | `3000` | Modern frontend with voice/text modes, form preview, Microsoft SSO |

---

## Key Features

The bot uses the **Model Context Protocol (MCP)** to interact with real-world USDA systems:

### Voice & Text Interaction

- **Dual Input Modes:** Switch seamlessly between voice and text via a toggle in the header.
- **Audio-Reactive UI:** Mic button with animated ripple rings that respond to voice input levels.
- **Filler Phrases:** Context-aware audio feedback (e.g., _"Checking current prices..."_) played during tool execution so users never hear silence.
- **Configurable Voice:** Choose between voices (Sarah / David), adjust speaking rate (0.5x–2.0x).
- **Streaming Responses:** Sentence-level TTS streaming for near-instant audio playback.

### Dynamic Form Filling

- **Universal Filling:** Automatically reads and understands _any_ PDF form dropped into the `Document/` folder (e.g., AD-2100, AD-1069).
- **Real-Time PDF Preview:** Side-by-side resizable panel shows the form being filled live as the farmer speaks.
- **Voice-Guided Collection:** Asks one field at a time with natural language questions, supports spelling mode, skip, and input validation (email, phone, ZIP, SSN, date).
- **Auto-Save:** Updates a "filled" copy of the PDF in real-time after each field update.
- **Email Delivery:** Send a single form or all filled forms in one email, with an auto-generated chat transcript PDF attached.
- **Progress Tracking:** Sticky progress bar shows filled vs. total fields.

### Market News (AMS)

- **Real-Time Prices:** Instant access to daily corn & soybean prices via USDA MARS API.
- **Local Bids:** Finds daily grain bids for specific states (e.g., "Iowa daily grain report").

### NASS Statistics

- **Production Data:** Queries NASS QuickStats for acreage, yield, and production history.
- **Rankings:** Ranks states/counties by commodity production (e.g., "Top corn states").

### Grants & Programs

- **Unified Search:** Searches across **139+ USDA programs** from 3 sources (FSA: 46, RD: 77, Deadlines: 16) in a single query with relevance scoring.
- **Eligibility Matching:** Matches farmers to grants based on their operation type and needs.
- **Source Filtering:** Optionally filter results by FSA, RD, or Deadline programs.

### Ag News & Alerts

- **State-Specific News:** Fetches the latest USDA press releases and FSA news for the farmer's specific state.
- **Disaster Alerts:** Checks for relevant disaster declarations and emergency program announcements.

### Service Locator

- **Find Help:** Locates the nearest FSA/NRCS service centers based on State/County.

### Chat Summary & Email

- **Proactive Summary:** On goodbye, the assistant offers to email a 3–5 bullet point summary of the session.
- **Transcript PDF:** Auto-generates a full chat transcript PDF (via reportlab) attached to the email.

### Cloud Logging & Recording

- **Session Transcripts:** Saves detailed chat logs (JSON) to Azure Blob Storage, organized by date (`YYYY-MM-DD/{session_id}.json`).
- **Audio Recording:** Optionally captures session audio (WAV) to Blob Storage.
- **Privacy First:** Users can say **"Stop recording"** at any time to halt audio capture and delete the current session's recordings.

---

## Tech Stack

| Layer     | Technology                                          | Version              |
| --------- | --------------------------------------------------- | -------------------- |
| Backend   | Python / aiohttp                                    | 3.11 / >=3.9.0       |
| LLM       | Azure OpenAI **Responses API** (with CoT reasoning) | `2025-04-01-preview` |
| STT / TTS | Azure Cognitive Services Speech SDK                 | >=1.41.0             |
| Frontend  | Next.js / React                                     | 16.1.6 / 19.2.3      |
| Auth      | NextAuth.js v5 + Microsoft Entra ID                 | ^5.0.0-beta.30       |
| Styling   | Tailwind CSS v4                                     | ^4                   |
| PDF       | pypdf (filling) + reportlab (generation)            | >=4.0.0              |
| Storage   | Azure Blob Storage                                  | >=12.0.0             |
| Caching   | cachetools (TTL-based, per-domain)                  | >=5.0.0              |
| Icons     | Lucide React                                        | ^0.576.0             |
| Markdown  | marked                                              | ^17.0.3              |

---

## Quick Start

### 1. Requirements

- **Docker** (Recommended) or Python 3.11+ & Node.js 18+
- **Azure OpenAI Service** (Responses API compatible deployment)
- **Azure Speech Service** (Key & Region)
- **Microsoft Entra ID App Registration** (for SSO authentication)
- **SMTP Account** (e.g., Gmail App Password) for sending completed forms
- **Azure Storage Account** (Connection String) for transcripts/recordings (Optional)

### 2. Configuration

Copy the example environment file and fill in your keys:

```bash
cp .env.example .env
```

**Required Variables:**

| Variable                         | Description                        |
| -------------------------------- | ---------------------------------- |
| `AZURE_OPENAI_ENDPOINT`          | Azure OpenAI endpoint URL          |
| `AZURE_OPENAI_API_KEY`           | Azure OpenAI API key               |
| `AZURE_OPENAI_DEPLOYMENT`        | Model deployment name              |
| `AZURE_SPEECH_KEY`               | Azure Speech Services key          |
| `AZURE_SPEECH_REGION`            | Azure Speech Services region       |
| `AUTH_SECRET`                    | NextAuth.js secret (random string) |
| `AUTH_MICROSOFT_ENTRA_ID_ID`     | Entra ID app client ID             |
| `AUTH_MICROSOFT_ENTRA_ID_SECRET` | Entra ID app client secret         |
| `AUTH_MICROSOFT_ENTRA_ID_ISSUER` | Entra ID issuer URL                |

**Optional Variables:**

| Variable                          | Default              | Description                    |
| --------------------------------- | -------------------- | ------------------------------ |
| `AZURE_SPEECH_VOICE`              | `en-US-JennyNeural`  | Default TTS voice              |
| `AZURE_API_VERSION`               | `2025-04-01-preview` | Azure OpenAI API version       |
| `ENABLE_RECORDINGS`               | `false`              | Enable audio capture           |
| `ENABLE_BLOB_LOGGING`             | `false`              | Enable Azure Blob logging      |
| `AZURE_STORAGE_CONNECTION_STRING` | —                    | Blob Storage connection string |
| `SMTP_HOST`                       | `smtp.gmail.com`     | SMTP server host               |
| `SMTP_PORT`                       | `587`                | SMTP server port               |
| `SMTP_USER`                       | —                    | SMTP username                  |
| `SMTP_PASSWORD`                   | —                    | SMTP password                  |
| `USDA_API_KEY`                    | —                    | USDA AMS data API key          |
| `NASS_API_KEY`                    | —                    | NASS QuickStats API key        |

### 3. Run with Docker

The easiest way to run the full stack:

```bash
docker compose up --build
```

This starts both services:

- **Voice Agent API** → http://localhost:8080
- **Next.js UI** → http://localhost:3000

Open your browser to **http://localhost:3000**, sign in with your Microsoft account, and start talking.

### 4. Run Locally (Development)

**Backend:**

```bash
pip install -r requirements.txt
cd src
python web_voice_agent.py
```

**Frontend:**

```bash
cd web_ui_nextjs
npm install
npm run dev
```

---

## Project Structure

```
├── docker-compose.yml              # Two-service container orchestration
├── Dockerfile                      # Multi-stage Python build (non-root)
├── requirements.txt                # Python dependencies
├── prompts/
│   └── USDA.yml                    # Voice persona & system prompt
├── Document/                       # PDF forms directory (auto-discovered)
├── src/
│   ├── web_voice_agent.py          # Main WebSocket server & orchestrator
│   ├── llm_stream.py              # Azure OpenAI Responses API (tool calling + CoT)
│   ├── stt_stream.py              # Speech-to-Text stream handler
│   ├── tts_stream.py              # Text-to-Speech stream handler
│   ├── config.py                  # Configuration & environment loading
│   ├── cache_manager.py           # TTL-based per-domain caching
│   ├── result_formatter.py        # Tool result truncation for LLM context
│   ├── blob_storage.py            # Azure Blob Storage (transcripts + audio)
│   └── mcp_tools/                 # MCP tool integrations
│       ├── form_tools.py          # Dynamic PDF filling & email delivery
│       ├── nass_tools.py          # NASS QuickStats (production/stats)
│       ├── usda_tools.py          # AMS Market News (prices)
│       ├── unified_programs_tools.py  # 139+ grants & programs search
│       ├── service_center_tools.py    # FSA/NRCS office locator
│       ├── news_tools.py          # Ag news & alerts
│       └── utils.py               # Shared utilities
├── web_ui_nextjs/                 # Next.js 16 frontend
│   ├── app/                       # App router (layout, page, API routes)
│   ├── auth.ts                    # Microsoft Entra ID SSO config
│   ├── components/
│   │   ├── Header.tsx             # Branding, mode toggle, connection status
│   │   ├── ChatContainer.tsx      # Chat messages, welcome screen, markdown
│   │   ├── Controls.tsx           # Mic button (voice) / textarea (text)
│   │   ├── FormPreviewPanel.tsx   # Resizable PDF preview side panel
│   │   ├── SettingsModal.tsx      # Voice & rate selection
│   │   └── ProfileMenu.tsx        # Sign in/out, user avatar
│   ├── hooks/
│   │   ├── useWebSocket.ts        # WebSocket client with auto-reconnect
│   │   ├── useAudioPlayer.ts      # TTS audio playback
│   │   ├── useAudioRecorder.ts    # Mic capture via AudioWorklet
│   │   └── useTheme.ts            # Dark/light theme toggle
│   └── public/
│       └── audio-processor.js     # AudioWorklet processor (16kHz PCM)
├── cache/                         # Pre-scraped USDA data (JSON)
│   ├── fsa_programs_comprehensive.json
│   ├── rd_programs_comprehensive.json
│   ├── program_deadlines_comprehensive.json
│   ├── service_centers_complete.json
│   ├── state_news_*.json
│   ├── us_counties.json
│   └── scripts/                   # Cache build & scraping scripts
└── images/                        # Architecture diagrams
```

---

## WebSocket Protocol

The backend communicates with the frontend over a single WebSocket connection at `/ws`.

**Client → Server:**

| Message Type                | Description                           |
| --------------------------- | ------------------------------------- |
| `session_start`             | Reset session state                   |
| `mic_activated`             | Trigger greeting on first mic use     |
| `input_audio_buffer.append` | Base64-encoded 16kHz PCM audio chunks |
| `text_message`              | Typed text input                      |
| `form_field_update`         | Manual form edits from the UI         |
| `update_settings`           | Change voice/rate settings            |
| `request_tts`               | Replay TTS for a previous message     |
| `ping`                      | Keep-alive (every 15s)                |

**Server → Client:**

| Message Type     | Description                         |
| ---------------- | ----------------------------------- |
| `session_id`     | 8-char hex session identifier       |
| `transcript`     | Finalized user speech transcription |
| `audio_chunk`    | Base64-encoded TTS audio            |
| `audio_complete` | End of TTS stream for a response    |
| `clear_audio`    | Interrupt / clear current playback  |
| `error`          | Error messages                      |
| `pong`           | Keep-alive response                 |

---

## Security & Privacy

- **Microsoft Entra ID SSO:** Enterprise-grade authentication via Azure AD; only authenticated users can access the UI.
- **No Data Retention:** Voice audio is processed in memory by default. If `ENABLE_RECORDINGS` is set, audio is saved to Azure Blob Storage.
- **User Control:** Users can explicitly opt-out of recording during a session by voice command, which immediately deletes that session's audio.
- **Secure Handling:** PDF forms are processed locally within the container and deleted after emailing.
- **Non-Root Container:** Docker image runs as `appuser` (UID 1000) with health checks.
- **Azure Security:** Relies on enterprise-grade Azure Cognitive Services.

---
