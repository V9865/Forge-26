# EmberRoute Deployment Guide (Hugging Face Spaces - Docker SDK)

This guide provides step-by-step instructions for deploying EmberRoute as a single Docker container on Hugging Face Spaces.

---

## 1. Create the Hugging Face Space

1. Log into your [Hugging Face](https://huggingface.co) account.
2. Navigate to **New Space** (`https://huggingface.co/new-space`).
3. Fill in the Space settings:
   - **Space name**: `EmberRoute` (or your preferred name)
   - **License**: `mit` or `apache-2.0`
   - **Space SDK**: Select **Docker** (Blank template)
   - **Space hardware**: Free CPU (2 vCPU, 16 GB RAM)
   - **Visibility**: Public (or Private during initial staging)
4. Click **Create Space**.

---

## 2. Configure Environment Secrets in Space Settings

> [!CAUTION]
> Never commit secrets or API keys to the Git repository. Always configure sensitive credentials using Hugging Face Spaces Secrets.

In your newly created Space:
1. Go to **Settings** $\to$ **Variables and secrets**.
2. Under **Secrets**, click **New secret** and add the following keys:

| Secret Name | Value | Description |
|:---|:---|:---|
| `FIRMS_MAP_KEY` | `<your-nasa-firms-map-key>` | Free NASA FIRMS map key from https://firms.modaps.eosdis.nasa.gov/api/ |
| `GROQ_API_KEY` | `<your-groq-api-key>` | Free Groq API key from https://console.groq.com |
| `LLM_CHAIN` | `groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant` | Model fallback chain for Hugging Face Space |
| `LLM_PLANNER_MODEL` | `groq:llama-3.1-8b-instant` | Low-latency model for agent tool calling loop |
| `LLM_BRIEFING_MODEL` | `groq:llama-3.3-70b-versatile` | High-capacity model for factual briefing synthesis |

> [!IMPORTANT]
> **Ollama Availability Note**:
> Local Ollama is **NOT available** on the free CPU tier of Hugging Face Spaces. In this container environment, the agent chain automatically resolves to **Groq**, with seamless, instant fallback to **deterministic planning and template briefings** if the external LLM is unreachable or exhausted.

---

## 3. Clone and Push to Space Repository

You can push the repository directly to your Hugging Face Space using Git:

```bash
# 1. Add Hugging Face Space as a git remote
git remote add space https://huggingface.co/spaces/<your-username>/<your-space-name>

# 2. Prepend HF_README_HEADER.md frontmatter to README.md if not already present
# (Ensure title, sdk: docker, and app_port: 7860 are at the top of README.md)

# 3. Push to Hugging Face Space
git push space main:main
```

Hugging Face Spaces will automatically detect the `Dockerfile`, build the multi-stage image, and start the container on port `7860`.

---

## 4. Verifying Container Health & Smoke Test

Run the verification smoke test against the live Space deployment URL:

```bash
# Test the deployed Hugging Face Space
python scripts/smoke_test.py https://<your-username>-<your-space-name>.hf.space
```

### Performance & Cold-Start Expectations:
- **Cold start duration**: ~10–15 s (container boots, loads Python packages, binds port 7860).
- **First plan execution duration**: ~45–60 s for a standard 0.2° x 0.2° AOI (fetches terrain elevation tiles, Open-Meteo wind vectors, OpenStreetMap road network, runs anisotropic Dijkstra fire arrival, and calculates time-dependent evacuation routes).
- **Subsequent identical requests**: < 100 ms (served from 60s SHA-256 parameter cache).

### Optimization & Caching Strategy:
If the first plan exceeds 60 seconds on free-tier CPU hardware:
1. **Resolution Tuning**: Set `resolution_m=90` or `120` in the request (reduces raster cell count from ~150k to ~50k cells).
2. **OSM Disk Caching**: The road graph is automatically cached to `.cache/osm/` on first download; subsequent runs in the same region bypass Overpass network latency entirely.
3. **Terrain Tile Caching**: AWS Terrarium elevation tiles are cached with 30-day TTLs.

