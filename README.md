---
title: EmberRoute
emoji: 🔥
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# EmberRoute: Wildfire Spread Prediction & Evacuation Routing

EmberRoute is an autonomous, physical wildfire simulation and time-dependent evacuation route planner built for emergency response officers and civil protection analysts.

It combines real-time physical fire spread modeling (anisotropic Rothermel equations), dynamic road graph hazard analysis (time-dependent Dijkstra on OpenStreetMap), and automated operational briefing generation powered by high-capacity LLMs (Groq).

---

## Key Capabilities

1. **Live Fire Intelligence & Cluster Detection**:
   - Queries real-time thermal anomaly data from NASA FIRMS (VIIRS/MODIS satellites).
   - Automatically clusters active hotspots using DBSCAN spatial clustering to establish areas of interest (AOIs).

2. **Physical Wildfire Spread Simulation**:
   - Anisotropic Rothermel surface fire spread calculation integrating:
     - High-resolution digital elevation models and slope aspect from AWS Terrarium terrain tiles.
     - Real-time meteorological wind speed and direction vectors from Open-Meteo.
     - Land cover fuel models from ESA WorldCover.
   - Computes time-dependent fire arrival contours (isochrones).

3. **Time-Dependent Evacuation Route Planning**:
   - Downloads real-world drivable road networks from OpenStreetMap (via `osmnx` and `networkx`).
   - Identifies threatened settlements and calculates viable egress corridors before fire arrival.
   - Detects cut routes and road segment breaches dynamically.

4. **Autonomous Monitoring & LLM Operational Briefings**:
   - Continuous background monitoring loop that tracks active clusters, detects trigger conditions, and updates simulations autonomously.
   - Synthesizes factual, structured operational briefings with Groq LLMs (Llama 3.3 70B Versatile / Llama 3.1 8B Instant) with deterministic template fallback.
   - Strict provenance tracking and empirical validation comparisons against historical satellite observations.

---

## System Architecture

```
┌────────────────────────────────────────────────────────┐
│              EmberRoute React Frontend                 │
│  MapLibre GL Map · Responsive Split Panels · A11y      │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP / JSON
┌───────────────────────────▼────────────────────────────┐
│                  FastAPI Backend Server                │
│                                                        │
│  ┌──────────────────┐  ┌────────────────────────────┐  │
│  │ Cluster Engine   │  │ Physical Simulation Engine │  │
│  │ (NASA FIRMS)     │  │ (Rothermel + AWS Terrain)  │  │
│  └──────────────────┘  └────────────────────────────┘  │
│  ┌──────────────────┐  ┌────────────────────────────┐  │
│  │ Road Routing     │  │ Autonomous Monitor & LLM   │  │
│  │ (OSM + Dijkstra) │  │ (Groq Briefing Synthesis)  │  │
│  └──────────────────┘  └────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## Quickstart & Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+ and npm
- (Optional) Docker for containerized deployment

### 1. Environment Configuration
Copy `.env.example` to `.env` and provide your API keys:
```bash
cp .env.example .env
```
Key configuration variables:
- `FIRMS_MAP_KEY`: Free map key from [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/)
- `GROQ_API_KEY`: Free API key from [Groq Console](https://console.groq.com)
- `LLM_CHAIN`: Model fallback chain (e.g., `groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant`)

### 2. Backend Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```
API documentation will be available at `http://127.0.0.1:8000/docs`.

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
The React development application will open at `http://localhost:5173`.

---

## Containerized Deployment (Docker / Hugging Face Spaces)

EmberRoute is packaged as a self-contained multi-stage Docker container listening on port `7860`.

### Build & Run Locally
```bash
# Build Docker image
docker build -t emberroute .

# Run container with environment file
docker run -p 7860:7860 --env-file .env emberroute
```

### Hugging Face Spaces Deployment
See [docs/deploy.md](docs/deploy.md) for step-by-step instructions on deploying EmberRoute as a Docker Space with encrypted secrets.

---

## Verification & Testing

EmberRoute includes comprehensive test suites and smoke test scripts:

```bash
# Run backend test suite
pytest

# Build and lint React frontend
cd frontend
npm run lint
npm run build

# Run end-to-end API smoke test (with local server running)
python scripts/api_smoke.py http://127.0.0.1:8000

# Run container deployment smoke test
python scripts/smoke_test.py http://localhost:7860
```

Refer to [docs/RELEASE_CHECK.md](docs/RELEASE_CHECK.md) for the complete pre-flight verification checklist.

---

## Operational Notice & Disclaimer

EmberRoute is an experimental research and emergency planning decision-support tool developed for hackathon evaluation. Physical simulation algorithms (Rothermel spread and time-dependent routing) are validated against historical satellite detections and meteorological reanalysis datasets. **This software does not constitute certified operational life-safety software or official evacuation routing advice.** Always adhere to directives issued by official emergency management authorities.

