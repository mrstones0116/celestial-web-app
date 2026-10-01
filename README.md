# 🌌 Celestial Web App - AI Stargazing & 3D Sky Visualization

A high-performance, browser-based 3D celestial sphere simulator with integrated AI-powered astrophotography recognition and conversational stargazing tours. Built with Three.js, FastAPI, Qwen-VL, and DeepSeek.

![Version](https://img.shields.io/badge/version-2.2-blue)
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

### 📷 AI-Powered Photo Identification
- **OpenCV Star Detection**: Median-background estimation + residual thresholding + connected-component analysis + bright-star de-duplication, with EXIF orientation fix and automatic downscaling for large images
- **Adaptive K-Means Clustering**: K-means++ with multi-initialization, silhouette-based automatic K selection, outputs main star, edge stars, and neighbor clusters per cluster
- **Multi-Version VL Input**: Sends original, brightened, inverted, and cluster-annotated images to the VL model for better faint-star recognition
- **Whole-Image VL Recognition**: Each cluster is judged independently using color mapping, main-star position, member weights, and neighbor relationships
- **Low-Confidence Recheck**: High-confidence clusters act as anchors; only low-confidence clusters are re-judged to keep the sky region physically self-consistent
- **Annotated Overlay**: Backend returns star-point and cluster-colored PNG overlays for frontend display
- **Debug Constellation Map**: With `DEBUG_VISION=1`, saves input / clustered / constellation-position annotated images to `backend/debug/`
- **88-Constellation Normalization**: VL-returned abbreviations or full names are normalized to IAU 3-letter abbreviations

### 🎬 AI Stargazing Tour
- **Natural-Language Planning**: Describe what you want to see in plain Chinese or English — "我想看夏季的星空" or "show me the Messier objects"
- **LLM Intent Recognition**: Powered by DeepSeek (or any OpenAI-compatible endpoint), with automatic fallback to keyword matching
- **Pre-Built Tour Templates**: Summer Triangle, Winter Orion, Bright Star Tour, Messier Marathon samples
- **Step-by-Step Narration**: Each stop includes short/long narration, observation tips, and camera focus hints
- **Session Management**: Server-side session store with TTL cleanup, pause / next / prev / stop controls
- **Altitude-Azimuth Annotation**: Each target is annotated with real-time alt/az for the observer's location and time

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
│   ├── server.py              # FastAPI API server + VL integration
│   ├── data_loader.py         # HYG star catalog loader (local-first + download fallback)
│   ├── download.py            # One-shot HYG download helper
│   ├── data/
│   │   └── hygdata_v41.csv    # ~35 MB, not committed (see Quick Start)
│   ├── vision/                # AI vision pipeline modules
│   │   ├── __init__.py
│   │   ├── pipeline.py        # Orchestration: detect → cluster → VL → recheck → annotate
│   │   ├── detection.py       # OpenCV star detection
│   │   ├── clustering.py      # Adaptive K-means + main/edge/neighbor computation
│   │   ├── annotate.py        # Star / VL / constellation-position annotation
│   │   ├── vl.py              # VL client + prompt builder + JSON parser
│   │   ├── constellations.py  # 88-constellation table + name normalization
│   │   └── config.py          # VisionConfig, env vars read once
│   ├── tour/                  # Conversational tour module
│   │   ├── api.py             # /api/tour/* endpoints
│   │   ├── astro_utils.py     # RA/Dec → Alt/Az, GMST
│   │   ├── llm_client.py      # DeepSeek-backed intent parser
│   │   ├── planner.py         # Intent → TourPlan
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
│   │   └── tour.js            # AI tour UI + API client
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
- **DeepSeek API Key** for the AI tour module ([Get one here](https://platform.deepseek.com)) — *optional, falls back to keyword matching*

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
| `VISION_TOP_N` | `100` | Max number of stars to keep |
| `VISION_MAX_UPLOAD_MB` | `20` | Upload size limit |
| `VISION_EDGE_MARGIN` | `0.10` | Edge crop ratio to avoid lens distortion |
| `VISION_DETECT_SIGMA` | `6.0` | Residual threshold in sigma units |
| `VISION_FORCED_K` | `0` / `None` | Force K if >= 2 |
| `VISION_MIN_K` | `2` | Minimum adaptive K |
| `VISION_MAX_K` | `8` | Maximum adaptive K |
| `VISION_KMEANS_N_INIT` | `10` | K-means multi-initialization count |
| `VISION_KMEANS_MAX_ITER` | `200` | K-means max iterations |
| `VISION_CLUSTER_MIN_STARS` | `3` | Minimum stars per cluster |
| `VISION_WEIGHT_BRIGHTNESS` | `0.65` | Brightness weight in member scoring |
| `VISION_WEIGHT_DISTANCE` | `0.35` | Distance-to-main-star weight |
| `VISION_CONFIDENCE_THRESHOLD` | `0.51` | Low-confidence recheck threshold |
| `VISION_VL_TIMEOUT` | `300` | VL request timeout (seconds) |
| `VISION_VL_MAX_RETRIES` | `4` | VL retry count |
| `VISION_VL_MAX_TOKENS` | `4000` | VL max output tokens |
| `DEBUG_VISION` | `0` | Set to `1` to save debug images |

### AI Tour Module (DeepSeek)

| Variable | Default | Description |
|---|---|---|
| `TOUR_LLM_API_KEY` | *(optional)* | DeepSeek API key. If unset, tour falls back to keyword matching |
| `TOUR_LLM_API_URL` | `https://api.deepseek.com/v1/chat/completions` | Chat completions endpoint |
| `TOUR_LLM_MODEL` | `deepseek-flash` | Model ID |
| `TOUR_LLM_ENABLED` | `1` | Set to `0` to disable LLM (keyword mode) |
| `TOUR_LLM_TIMEOUT` | `15` | Request timeout in seconds |

## 📸 AI Identification Pipeline

```
Photo Upload
    ↓
detect_stars
    - EXIF transpose, longest-edge resize, grayscale
    - Gaussian blur + median background estimation
    - Residual threshold + connected-component analysis
    - Sort by flux + min-distance de-duplication
    ↓
cluster_stars
    - K-means++ with multi-initialization
    - Adaptive K in [MIN_K, MAX_K]
    - Silhouette score picks best K
    - Compute main star, edge stars, neighbors, member weights
    ↓
annotate_stars
    - Frontend display image: star points + cluster colors
    ↓
prepare_versions
    - Original / brightened / inverted
    ↓
annotate_clusters_for_vl
    - VL input image: C0~Cn labels + main-star big-circle white-dot
    ↓
VLClient.chat_json
    - Whole-image judgment of each cluster's constellation
    - Returns constellation / abbr / confidence / alternative
    ↓
parse_vl_item + normalize_constellation
    - Normalize to 88-constellation 3-letter abbreviations
    ↓
_vl_recheck
    - Low-confidence clusters re-judged with high-confidence anchors
    ↓
Write back stars[i].cluster
    ↓
DEBUG_VISION=1
    - Save input / clusters / constellations debug images
    ↓
Response
    - stars / clusters / vl_clusters / vl_summary / vl_recheck / annotated_image
```

## 🎬 AI Tour Pipeline

```
User types: "Summer sky"
    ↓
POST /api/tour/sessions            → create session
    ↓
POST /api/tour/sessions/{id}/instruction
    ↓
llm_client.parse_instruction       → {"intent": "summer_sky", "source": "llm"}
    ↓  (on any error)
planner.detect_intent              → keyword fallback
    ↓
planner.build_plan(intent, config) → TourPlan with steps
    ↓
astro_utils.annotate_plan          → fill altitude_deg / azimuth_deg per target
    ↓
Response { plan, current_step_index: 0 }
    ↓
Tour UI renders step 1; "下一步" triggers /next
```

### Tour API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/tour/sessions` | Create a session |
| `POST` | `/api/tour/sessions/{id}/instruction` | Submit a natural-language request |
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
| Tour LLM | DeepSeek Flash (OpenAI-compatible API) |
| Image Processing | OpenCV + NumPy + Pillow |
| Clustering | Adaptive K-means / K-means++ / Silhouette |
| Star Catalog | HYG Database v41 |
| Desktop Wrapper | PyWebView |
| Charts | Custom Canvas 2D RA-Dec projection |

## 📝 Development Notes

- **Star coordinates** use J2000 epoch internally; precession matrix applied per-frame based on simulation time
- **Constellation lines** load from local GeoJSON first, fall back to [d3-celestial](https://github.com/ofrohn/d3-celestial) CDN
- **Planet positions** use Meeus low-precision solar theory + JPL orbital elements; accurate to ~1 arcmin for 1800–2050
- **Moon phase** computed from Sun-Moon elongation angle, rendered procedurally on canvas texture each frame
- **Sky color** uses smoothstep-interpolated color stops across 9 altitude breakpoints to avoid RGB mud at twilight transitions
- **HYG loading** is local-first: reads `backend/data/hygdata_v41.csv` if present, otherwise downloads and caches it
- **Star detection**: `detection.py` uses median background + residual threshold + connected components; edges are cropped, bright stars de-duplicated by min distance
- **Clustering**: `clustering.py` tries K in `MIN_K~MAX_K`, sorts by silhouette desc with small-K tie-break to avoid over-segmentation
- **Cluster payload**: each cluster contains `main_star`, `stars`, `edge_stars`, `neighbors`, `bbox`, `avg_brightness`
- **VL inputs**: `prepare_versions` builds original / brightened / inverted; `annotate_clusters_for_vl` builds the C-numbered cluster map with main-star markers
- **VL recheck**: after the first pass, clusters below `VISION_CONFIDENCE_THRESHOLD` are re-judged with high-confidence clusters as anchors
- **Debug**: with `DEBUG_VISION=1`, saves `*_input.png`, `*_k*_clusters.png`, `*_k*_constellations.png`
- **Central config**: all env vars are read once in `VisionConfig` (`vision/config.py`)
- **Tour LLM** is fully optional: if no key is configured, `planner.detect_intent` handles Chinese/English keyword matching

## 🤝 Contributing

Contributions are welcome! Areas of interest:
- Plate solving / WCS calibration for precise photo-to-sky alignment
- Additional DSO catalogs (Caldwell, Sharpless)
- More tour templates (planets, moon phases, constellation mythology)
- Mobile-responsive touch controls
- Multi-language UI support

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [HYG Star Catalog](https://www.astronexus.com/hyg) — Stellar data
- [d3-celestial](https://github.com/ofrohn/d3-celestial) — Constellation line data
- [ModelScope](https://modelscope.cn) — Qwen-VL model hosting
- [DeepSeek](https://platform.deepseek.com) — Tour intent LLM
- [Three.js](https://threejs.org) — WebGL rendering engine

---
