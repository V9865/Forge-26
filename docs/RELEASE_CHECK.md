# EmberRoute Pre-Flight Release & Verification Checklist

This document details the complete end-to-end quality assurance and verification procedure for releasing EmberRoute and deploying to Hugging Face Spaces.

---

## 1. Environment & Git State Inspection

Before running checks, verify clean working tree and proper branch tracking:

```bash
# Verify current branch and repository status
git status
git branch -vv
```

**Acceptance Criteria**:
- Working tree clean or containing only intended release modifications.
- Branch tracks the designated milestone or release branch.

---

## 2. Frontend Build, Typecheck & Linting

Verify that static assets compile cleanly without TypeScript or linting errors:

```bash
# Navigate to frontend directory
cd frontend

# Run Oxlint for code quality and accessibility static analysis
npm run lint

# Compile TypeScript and build production bundle
npm run build
```

**Acceptance Criteria**:
- `npm run lint`: Exits with code 0 (0 errors, 0 warnings).
- `npm run build`: Exits with code 0; generates production bundles in `frontend/dist/` (`index.html`, CSS, and JS chunks including lazy-loaded MapLibre chunk).

---

## 3. Backend Unit & Integration Tests

Run the pytest suite to validate core physical modeling, routing, and API schemas:

```bash
# Activate Python environment
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate

# Run all test suites
pytest -v
```

### Test Classification:
- **Offline / Procedural Tests** (`tests/unit/`):
  - `test_spread.py`: Anisotropic Rothermel fire spread calculation on procedural elevation grids.
  - `test_osm.py`: Time-dependent Dijkstra routing and route cut detection on synthetic road graphs.
  - `test_cache.py`: Cache key hashing, TTL expiration, and fallback mechanics.
  - `test_agent.py`: Agent briefing synthesis fallback, token budget discipline, and prompt formatting.
- **Integration & Live Feed Tests** (`tests/integration/`, `tests/api/`):
  - Requires network access and valid `FIRMS_MAP_KEY` / `GROQ_API_KEY`.
  - To run only offline unit tests without network:
    ```bash
    pytest tests/unit/ -v
    ```

**Acceptance Criteria**:
- All unit and mock integration tests pass (100% passing tests).

---

## 4. API End-to-End Smoke Test

With the FastAPI server running locally, verify all API endpoints and job polling:

```bash
# Terminal 1: Start backend server
uvicorn api.main:app --port 8000

# Terminal 2: Run automated API smoke script
python scripts/api_smoke.py http://127.0.0.1:8000
```

**Smoke Test Sequence**:
1. Checks root (`/`) and OpenAPI specification (`/openapi.json`).
2. Queries diagnostics health endpoint (`GET /api/health`).
3. Queries active fire clusters (`GET /api/clusters?hours=24`).
4. Submits physical simulation job (`POST /api/plan`) in SCENARIO mode.
5. Polls job progress (`GET /api/jobs/{id}`) to completion (`status="done"`).
6. Validates response payload against Pydantic schema (`PlanResult`).
7. Checks autonomous monitor (`GET /api/monitor`), assumptions (`GET /api/assumptions`), and empirical validation (`GET /api/validation`).

**Acceptance Criteria**:
- All 6 verification steps return `PASS`. Script exits with code 0.

---

## 5. Docker Containerization & HF Spaces Deployment

Verify the multi-stage container build and healthcheck probe:

```bash
# 1. Build container image from project root
docker build -t emberroute .

# 2. Run container locally on standard HF Spaces port
docker run -d -p 7860:7860 --name emberroute-test --env-file .env emberroute

# 3. Execute container deployment smoke test
python scripts/smoke_test.py http://localhost:7860

# 4. Stop and remove test container
docker stop emberroute-test && docker rm emberroute-test
```

**Acceptance Criteria**:
- Docker multi-stage build finishes with exit code 0 without errors.
- Stage 1 builds React frontend from source into `/app/frontend/dist`.
- Stage 2 copies built assets to `/app/frontend/dist` and installs Python dependencies.
- Container healthcheck (`curl -f http://localhost:7860/api/health`) reports healthy.
- `scripts/smoke_test.py` passes all checks against port 7860.

---

## 6. Pre-Release Acceptance Sign-off Matrix

| Verification Check | Target Component | Success Condition | Verified? |
|:---|:---|:---|:---:|
| Frontend Lint | `frontend/src/**` | 0 errors, 0 warnings | [x] |
| Frontend Production Build | `frontend/dist/` | Vite build succeeds | [x] |
| Mobile Drawer Focus & Trap | `AppLayout.tsx` | Close button focused on open; Tab contained | [x] |
| Validation Tabs Roving Tabindex | `ValidationPanel.tsx` | Arrow/Home/End keyboard navigation functional | [x] |
| Multi-Stage Dockerfile | `Dockerfile` | Builds frontend from source; strict build | [x] |
| Docker Context Filter | `.dockerignore` | Ignores `.env`, `node_modules`, `frontend/dist` | [x] |
| Space Metadata | `README.md` | Retains YAML frontmatter (Docker SDK, port 7860) | [x] |
| API Schemas Integrity | `api/schemas.py` | Unchanged frozen contract | [x] |
| Backend Core Integrity | `core/**`, `api/**` | Untouched, no unauthorized modifications | [x] |

