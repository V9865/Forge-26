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

EmberRoute is an autonomous, physical wildfire simulation and time-dependent evacuation route planner built for emergency response officers.

## Deployment on Hugging Face Spaces
This Space runs as a single Docker container integrating:
- **FastAPI Backend**: Real-time physical simulation, anisotropic Rothermel spread engine, time-dependent Dijkstra road network routing, and LLM-assisted operational briefing synthesis.
- **React Frontend**: Interactive MapLibre GL mapping, time-slider arrival bands, and evacuation route tables.

See `docs/deploy.md` for complete configuration and secret management instructions.

