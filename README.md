# 🌌 Celestial Web App - AI Stargazing & 3D Sky Visualization

A high-performance, browser-based 3D celestial sphere simulator with integrated AI-powered astrophotography recognition (plate solving) and conversational stargazing tours. Built with Three.js, FastAPI, Qwen-VL, and DeepSeek.

![Version](https://img.shields.io/badge/version-2.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.9+-yellow)
![Three.js](https://img.shields.io/badge/three.js-r128-orange)

## ✨ Key Features

### 🔭 Real-Time 3D Celestial Sphere
- **Horizon Coordinate System (Alt-Az)**: Physically accurate diurnal motion based on observer location and time
- **88 IAU Constellations**: Standard stick-figure lines loaded from GeoJSON with precession correction
- **Solar System**: Real-time planetary positions using JPL ephemeris approximations (1800–2050 AD)
- **Dynamic Moon Phases**: Procedurally rendered lunar terminator with accurate illumination percentage
- **Atmospheric Rendering**: Smooth sky gradient transitions from astronomical twilight through golden hour to daylight
- **Deep Sky Objects**: Messier/NGC/IC catalog with angular-size-scaled ring markers
- **Interactive Controls**: Drag to rotate, scroll to zoom (4°–110° FOV), click any object for detailed info panel

### 📷 AI Star Map Plate Solver
- **OpenCV Star Detection**: Median-background estimation + residual thresholding + connected-component analysis + bright-star de-duplication, with EXIF orientation fix and automatic downscaling
- **VL Semantic Recognition**: Qwen-VL identifies **which constellations are visible** (3-letter abbreviations only) — no pixel regression, no hallucinated coordinates
- **HYG Catalog Lookup**: Member stars (RA/Dec/magnitude) retrieved from HYG v41 for each identified constellation
- **Plate Solving**: RANSAC + ICP fits a similarity transform that projects HYG catalog coordinates **precisely onto detected image stars**
  - Complex-number representation (4-DOF: scale / rotation / translation)
  - **One-to-one inlier matching** prevents multiple template stars collapsing onto a single bright spot
  - **Scale prior** derived from template angular span × image diagonal
  - **LO-RANSAC** local optimization + **ICP** refinement
- **Faithful Rendering**: Constellation skeleton lines from `constellations.lines.json` drawn through the fitted transform, aligned with the actual bright stars in the photo
- **Chinese Font Support**: Auto-detects system CJK fonts (msyh / simhei / PingFang / Noto CJK)
- **Star Names**: Proper names when available, falls back to Bayer designations (`Betelgeuse` → `α Ori`)

### 🎬 AI Stargazing Tour
- **Snapshot-Driven Planning**: Reads the live sky state from the 3D scene (visible constellations, planets, Messier objects, sun altitude) and asks the LLM to plan a tour — **no user input required**
- **Natural-Language Planning**: Also accepts free-form requests like "我想看夏季的星空" or "show me the Messier objects"
- **Reasoning-Model Ready**: Full support for DeepSeek V4-series and other thinking models — automatically falls back to `reasoning_content` when `content` is empty, and enforces JSON output via `response_format`
- **Structured JSON Guarantee**: Uses `response_format={"type": "json_object"}` with automatic 400-downgrade retry for compatibility layers that don't support it
- **Configurable Token Budget**: Per-call `max_tokens` overridable via env vars, tuned for both reasoning and non-reasoning models
- **Pre-Built Tour Templates**: Summer Triangle, Winter Orion, Bright Star Tour, Messier Marathon samples
- **Step-by-Step Narration**: Each stop includes short/long narration, observation tips, best viewing window, cultural story, and camera focus hints
- **Session Management**: Server-side session store with TTL cleanup, pause / next / prev / stop controls
- **Altitude-Azimuth Annotation**: Each target is annotated with real-time alt/az for the observer's location and time
- **Graceful Fallback**: If the LLM is unreachable, a local planner builds a tour from the current sky state

### 🕐 Time & Location Control
- Full date/time editor with adjustable simulation speed (0.5× to 10×)
- Preset locations (Hong Kong, Beijing, Tokyo, NYC, London, Sydney, poles, equator)
- Browser GPS integration
- Local Sidereal Time (LST) and epoch display
- Precession-aware star positions for historical/future epochs

## 🏗️ Architecture

```
celestial-web-app/
├── backend/
│   ├── server.py              # FastAPI API server (pure adapter)
│   ├── data_loader.py         # HYG star catalog loader (local-first + download fallback)
│   ├── download.py            # One-shot HYG download helper
│   ├── data/
│   │   └── hygdata_v41.csv    # ~35 MB, not committed (see Quick Start)
│   ├── vision/                # AI vision pipeline
│   │   ├── __init__.py
│   │   ├── pipeline.py        # Orchestration: detect → VL → plate solve → render
│   │   ├── detection.py       # OpenCV star detection
│   │   ├── plate_solve.py     # RANSAC + ICP similarity fit (HYG → image pixels)
│   │   ├── projection.py      # Gnomonic projection helpers
│   │   ├── constellation_catalog.py  # HYG members + GeoJSON skeleton lines
│   │   ├── annotate.py        # Star map / constellation projection rendering
│   │   ├── vl.py              # VL client + prompt + robust JSON parsing
│   │   ├── constellations.py  # 88-constellation name normalization
│   │   └── config.py          # VisionConfig, env vars read once
│   ├── tour/                  # Conversational tour module
│   │   ├── api.py             # /api/tour/* endpoints
│   │   ├── astro_utils.py     # RA/Dec → Alt/Az, GMST
│   │   ├── llm_client.py      # DeepSeek-backed intent parser + snapshot planner
│   │   ├── planner.py         # Intent → TourPlan, LLM JSON → TourPlan
│   │   ├── schemas.py         # Pydantic models
│   │   ├── session_store.py   # In-memory session store (TTL)
│   │   └── templates.py       # Built-in tour routes
│   ├── requirements.txt
│   └── .env.example           # Environment variable template
├── frontend/
│   ├── index.html             # Main UI shell
│   ├── js/
│   │   ├── scene3d.js         # Three.js celestial renderer (~2800 LOC)
│   │   ├── chart2d.js         # 2D RA-Dec projection chart
│   │   ├── app.js             # UI bindings & data management
│   │   ├── time.js            # Time simulation engine
│   │   ├── search.js          # Star search with autocomplete
│   │   ├── dso.js             # Deep sky object catalog
│   │   └── tour.js            # AI tour UI + snapshot prompt builder
│   ├── vision.js              # Photo identification UI + modal
│   ├── css/style.css          # Dark theme styling
│   └── data/
│       └── constellations.lines.json  # 88 constellation GeoJSON
└── main.py                    # PyWebView desktop launcher
```

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Node.js (optional, for frontend dev)
- **ModelScope API Key** for photo identification ([Get one here](https://modelscope.cn/my/myaccesstoken))
- **DeepSeek API Key** for the AI tour module ([Get one here](https://platform.deepseek.com)) — *optional, falls back to local planning*

### Installation

```bash
# Clone repository
git clone https://github.com/mrstones0116/celestial-web-app.git
cd celestial-web-app

# Create virtual environment
python -m venv astro_env
source astro_env/bin/activate  # Linux/Mac
# astro_env\Scripts\activate   # Windows

# Install dependencies
pip install -r backend/requirements.txt

# Configure API keys
cp backend/.env.example backend/.env
# Edit backend/.env and fill in your tokens

# Download HYG star catalog (~35 MB)
cd backend
python download.py
cd ..
```

### Running

```bash
# Launch desktop app (PyWebView)
python main.py

# Or run backend only (for browser access)
cd backend
uvicorn server:app --host 0.0.0.0 --port 8000
# Then open http://localhost:8000/
```

## ⚙️ Configuration

All configuration lives in `backend/.env`:

### Photo Identification (ModelScope / Qwen-VL)

| Variable | Default | Description |
|---|---|---|
| `MODELSCOPE_API_KEY` / `ZHIPU_API_KEY` | *(required)* | ModelScope or Zhipu access token; either one works |
| `ZHIPU_API_URL` | `https://api-inference.modelscope.cn/v1/chat/completions` | VL endpoint |
| `VL_MODEL` | `Qwen/Qwen3.8-Flash-Next` | Vision-language model ID (override for your deployment) |
| `VISION_MAX_DIM` | `1280` | Longest-edge resize before detection |
| `VISION_TOP_N` | `50` | Max number of stars to keep |
| `VISION_MAX_UPLOAD_MB` | `20` | Upload size limit |
| `VISION_EDGE_MARGIN` | `0.10` | Edge crop ratio to avoid lens distortion |
| `VISION_DETECT_SIGMA` | `10.0` | Residual threshold in sigma units |
| `VISION_CONFIDENCE_THRESHOLD` | `0.51` | Low-confidence marking threshold |
| `VISION_MIN_CONFIDENCE_KEEP` | `0.20` | Hard floor — results below are discarded |
| `VISION_VL_TIMEOUT` | `300` | VL request timeout (seconds) |
| `VISION_VL_MAX_RETRIES` | `4` | VL retry count |
| `VISION_VL_MAX_TOKENS` | `4000` | VL max output tokens |
| `DEBUG_VISION` | `0` | Set to `1` to save debug images |

### Plate Solving

| Variable | Default | Description |
|---|---|---|
| `VISION_CATALOG_MAX_MAG` | `5.0` | Max magnitude for constellation member stars |
| `VISION_PLATE_TEMPLATE_MAG` | `4.5` | Max magnitude for plate-solving template stars |
| `VISION_PLATE_RANSAC_ITER` | `6000` | RANSAC iterations |
| `VISION_PLATE_EPS_PX` | `6.0` | Inlier distance threshold (pixels) |
| `VISION_PLATE_MIN_INLIERS` | `3` | Minimum inliers to accept a solution |
| `VISION_PLATE_ICP_ITER` | `10` | ICP refinement iterations |
| `VISION_PLATE_DRAW_ALL_STARS` | `1` | Draw all member stars (outline) in addition to skeleton endpoints |

### AI Tour Module (DeepSeek)

| Variable | Default | Description |
|---|---|---|
| `TOUR_LLM_ENABLED` | `1` | Set to `0` to disable LLM entirely (local planner only) |
| `TOUR_LLM_API_KEY` | *(optional)* | DeepSeek API key. If unset, the local planner handles all requests |
| `TOUR_LLM_API_URL` | `https://api.deepseek.com/v1/chat/completions` | Chat completions endpoint |
| `TOUR_LLM_MODEL` | `deepseek-chat` | Model ID. Use `deepseek-reasoner` for reasoning models |
| `TOUR_LLM_TIMEOUT` | `120` | Base request timeout in seconds (overridden per call for skeleton) |
| `TOUR_LLM_MAX_TOKENS_PARSE` | `4000` | Token budget for intent parsing |
| `TOUR_LLM_MAX_TOKENS_NARRATION` | `8000` | Token budget for single-target narration |
| `TOUR_LLM_MAX_TOKENS_BATCH` | `32000` | Token budget for batch narration (all stops at once) |
| `TOUR_LLM_MAX_TOKENS_SKELETON` | `64000` | Token budget for the snapshot tour skeleton (reasoning models need headroom) |

> **Reasoning models**: The client automatically falls back to `reasoning_content` when `content` is empty (common with DeepSeek V4-series when the token budget is exhausted by the thinking chain), and enforces JSON output via `response_format={"type": "json_object"}` with automatic 400-downgrade retry. If your endpoint rejects `response_format`, the client retries once without it.

## 📸 AI Identification Pipeline

```
Photo Upload
    ↓
detect_stars  (OpenCV)
    - EXIF transpose, longest-edge resize, grayscale
    - Gaussian blur + median background estimation
    - Residual threshold + connected-component analysis
    - Sort by flux + min-distance de-duplication
    ↓
prepare_versions
    - Original / brightened / inverted (for VL input)
    ↓
VLClient.chat_json  (Qwen-VL)
    - Whole-image semantic recognition
    - Returns: constellation 3-letter abbreviations only
    - NO pixel coordinates, NO bboxes
    ↓
parse_constellation_item
    - Normalize to IAU abbreviations
    - Filter by confidence, cap at 8 constellations
    ↓
ConstellationCatalog
    - HYG v41 member stars (mag < 5.0) for each constellation
    - GeoJSON skeleton lines for drawing
    ↓
plate_solve  (RANSAC + ICP)
    1. Gnomonic projection of template stars around centroid
    2. Similarity transform b = w·a + t  (complex, 4-DOF)
    3. RANSAC:
         - Sample 2+2 point pairs
         - Scale prior: s ∈ [0.15·s_nom, 3·s_nom]
         - One-to-one inlier matching (each bright spot consumed once)
         - LO-RANSAC: local LS refinement after each hypothesis
    4. ICP refinement:
         - Re-match all template stars to image points
         - Least-squares similarity fit on inliers
         - Iterate until convergence
    ↓
render_constellation_reference
    - Skeleton lines projected through fitted transform
    - Endpoint stars matched to HYG nearest neighbors (< 0.5°)
    - Star labels: proper name → Bayer designation fallback
    - Chinese font auto-detection
    ↓
Response
    - stars / constellations / plate_solve / annotated_image
```

## 🎬 AI Tour Pipeline

```
Frontend reads live sky state (visible objects, sun altitude, time, location)
    ↓
tour.js.buildPrompt(skyState)      → structured Chinese report ("实时星空观测报告")
    ↓
POST /api/tour/sessions            → create session
    ↓
POST /api/tour/sessions/{id}/instruction   (snapshot detected by marker)
    ↓
llm_client._generate_skeleton      → LLM returns 4–6 step JSON skeleton
    ↓  (if content empty, falls back to reasoning_content)
llm_client.generate_batch_narration → per-stop narration (short/long/best_time/cultural_story/tip/fun_fact)
    ↓
planner.build_plan_from_llm_response → TourPlan Pydantic model
    ↓
Response { plan, current_step_index: 0 }
    ↓
Tour UI renders step 1; camera flies to target; "下一步" triggers /next
    ↓  (on any LLM failure)
tour.js._localPlan(skyState)       → local fallback tour (planets → constellations → DSOs)
```

### Tour API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/tour/sessions` | Create a session |
| `POST` | `/api/tour/sessions/{id}/instruction` | Submit a snapshot report or natural-language request |
| `POST` | `/api/tour/sessions/{id}/next` | Advance to next step |
| `POST` | `/api/tour/sessions/{id}/prev` | Go back one step |
| `POST` | `/api/tour/sessions/{id}/pause` | Pause the tour |
| `POST` | `/api/tour/sessions/{id}/stop` | Stop and close the session |

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| 3D Renderer | Three.js r128 (custom Alt-Az horizon system) |
| Backend API | FastAPI + Uvicorn |
| VL Model | Qwen/Qwen3.8-Flash-Next (overridable via `VL_MODEL`) |
| Tour LLM | DeepSeek Chat / DeepSeek Reasoner (OpenAI-compatible API) |
| Image Processing | OpenCV + NumPy + Pillow |
| Plate Solving | Custom RANSAC + ICP (NumPy, complex-number similarity) |
| Star Catalog | HYG Database v41 |
| Desktop Wrapper | PyWebView |
| Charts | Custom Canvas 2D RA-Dec projection |

## 🧠 Why Plate Solving Instead of Clustering

Constellations are **human-defined regions** of the celestial sphere — they don't exist as natural clusters in pixel data. Unsupervised clustering (K-means, DBSCAN, HDBSCAN) finds "where stars are dense", which has no semantic relationship to constellation boundaries. On a wide-field photo the clustering will happily cut Orion in half and glue Taurus to Auriga.

The correct approach has three stages:

1. **VL provides semantics**: "which constellations can you recognize in this photo?"
2. **Catalog provides geometry**: HYG gives exact RA/Dec for every member star
3. **RANSAC provides alignment**: fits the transform that maps catalog → image

This cleanly separates "what is in the image" (VL) from "where is it" (geometry), and eliminates VL's well-known weakness at pixel-coordinate regression.

## 📝 Development Notes

- **Star coordinates** use J2000 epoch internally; precession matrix applied per-frame based on simulation time
- **Constellation lines** load from local GeoJSON first, fall back to [d3-celestial](https://github.com/ofrohn/d3-celestial) CDN
- **Planet positions** use Meeus low-precision solar theory + JPL orbital elements; accurate to ~1 arcmin for 1800–2050
- **Moon phase** computed from Sun-Moon elongation angle, rendered procedurally on canvas texture each frame
- **Sky color** uses smoothstep-interpolated color stops across 9 altitude breakpoints to avoid RGB mud at twilight transitions
- **HYG loading** is local-first: reads `backend/data/hygdata_v41.csv` if present, otherwise downloads and caches it
- **Star detection**: `detection.py` uses median background + residual threshold + connected components; edges are cropped, bright stars de-duplicated by min distance
- **Constellation catalog**: loaded lazily after `loader.load_data()` completes; `proper` name preferred, `bf` (Bayer designation) as fallback
- **Plate solving scale prior**: `s_nominal = image_diagonal / template_angular_span`, allowed range `[0.15·s, 3·s]` — rejects degenerate solutions where all templates collapse onto one bright spot
- **One-to-one matching**: greedy assignment by distance ensures each image point is used at most once; this is essential for multi-constellation scenes
- **Debug images**: with `DEBUG_VISION=1`, saves `*_input.png`, `*_stars.png`, `*_constellations.png`
- **Central config**: all env vars read once in `VisionConfig` (`vision/config.py`)
- **Tour LLM** is fully optional: if no key is configured, `tour.js._localPlan()` builds a tour from the live sky state
- **Reasoning models**: `llm_client._post_chat()` normalizes responses by falling back to `reasoning_content` when `content` is empty, and enforces JSON via `response_format` with auto-downgrade on 400. Diagnostic logs print `model / finish / usage / content_len / reasoning_len` for every call
- **Token budget tuning**: if you switch between reasoning and non-reasoning models, adjust `TOUR_LLM_MAX_TOKENS_*` — reasoning models need 4–10× headroom because the thinking chain consumes the budget before `content` starts

## 🤝 Contributing

Contributions are welcome! Areas of interest:
- Wide-field distortion models (currently similarity transform only — TAN/SIP would help > 30° FOV)
- Multi-frame stacking & joint plate solving
- Additional DSO catalogs (Caldwell, Sharpless)
- More tour templates (planets, moon phases, constellation mythology)
- Mobile-responsive touch controls
- Multi-language UI support
- Streaming tour narration (currently waits for full JSON response)

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [HYG Star Catalog](https://www.astronexus.com/hyg) — Stellar data
- [d3-celestial](https://github.com/ofrohn/d3-celestial) — Constellation line data
- [ModelScope](https://modelscope.cn) — Qwen-VL model hosting
- [DeepSeek](https://platform.deepseek.com) — Tour intent LLM
- [Three.js](https://threejs.org) — WebGL rendering engine
```
