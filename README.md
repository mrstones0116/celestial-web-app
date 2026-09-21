# 🌌 Celestial Web App - AI Stargazing & 3D Sky Visualization

A high-performance, browser-based 3D celestial sphere simulator with integrated AI-powered astrophotography recognition. Built with Three.js, FastAPI, and Qwen-VL multimodal models.

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

### 📷 AI-Powered Photo Identification
- **Dual-Image Analysis**: Sends both original photo and CLAHE-enhanced dark-adapted version to VL model
- **Multi-Constellation Recognition**: Identifies all visible constellations in a single frame, not just the brightest
- **Skeleton Star Filtering**: Returns only named bright stars per constellation — no HD/HIP/HR numeric designations
- **Annotated Overlay**: Backend generates bounding boxes and labels directly on the enhanced image
- **Zoomable Modal**: Center-screen popup with scroll-wheel zoom, pan, and one-click PNG save
- **3D Cross-Highlighting**: Automatically focuses the 3D scene on identified stars with flash animation
- **Anti-Hallucination Pipeline**: Two-stage VL review + HYG catalog cross-validation prevents false positives

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
│   ├── data_loader.py         # HYG star catalog loader
│   ├── vision/                # AI vision pipeline modules
│   │   ├── star_detector.py   # OpenCV star point detection
│   │   ├── skeleton_matcher.py# Constellation skeleton matching
│   │   └── ...
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
│   │   └── dso.js             # Deep sky object catalog
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
- ModelScope API Key ([Get one here](https://modelscope.cn/my/myaccesstoken))

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

# Configure API key
cp backend/.env.example backend/.env
# Edit backend/.env and add your ModelScope token
```

### Running

```bash
# Launch desktop app (PyWebView)
python main.py

# Or run backend only (for browser access)
cd backend
uvicorn server:app --host 0.0.0.0 --port 8000
# Then open http://localhost:8000/frontend/index.html
```

## ⚙️ Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `MODELSCOPE_API_KEY` | *(required)* | ModelScope access token for Qwen-VL |
| `VL_MODEL` | `Qwen/Qwen3-VL-8B-Instruct` | Vision-language model ID |
| `VERIFY_MAX_MAG` | `6.5` | Max magnitude for HYG cross-validation |
| `DEBUG_VISION` | `0` | Set to `1` to save debug images |

## 📸 AI Identification Pipeline

```
Photo Upload
    ↓
CLAHE Enhancement (LAB L-channel)
    ↓
Qwen-VL Dual-Image Analysis
    ↓
Stage 1: Initial Recognition → Season + Constellations + Bright Stars + BBox
    ↓
Stage 2: Self-Review → Remove hallucinations, validate evidence
    ↓
HYG Catalog Cross-Check → Skeleton star filtering (no numeric IDs)
    ↓
Backend Annotation → Draw bbox + labels on enhanced image
    ↓
Frontend Display → Result list + Zoomable modal + 3D highlight
```

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| 3D Renderer | Three.js r128 (custom Alt-Az horizon system) |
| Backend API | FastAPI + Uvicorn |
| AI Model | Qwen3-VL-8B-Instruct (ModelScope) |
| Image Processing | OpenCV (CLAHE, star detection) |
| Star Catalog | HYG Database v3 |
| Desktop Wrapper | PyWebView |
| Charts | Custom Canvas 2D RA-Dec projection |

## 📝 Development Notes

- **Star coordinates** use J2000 epoch internally; precession matrix applied per-frame based on simulation time
- **Constellation lines** load from local GeoJSON first, fall back to [d3-celestial](https://github.com/ofrohn/d3-celestial) CDN
- **Planet positions** use Meeus low-precision solar theory + JPL orbital elements; accurate to ~1 arcmin for 1800–2050
- **Moon phase** computed from Sun-Moon elongation angle, rendered procedurally on canvas texture each frame
- **Sky color** uses smoothstep-interpolated color stops across 9 altitude breakpoints to avoid RGB mud at twilight transitions

## 🤝 Contributing

Contributions are welcome! Areas of interest:
- Plate solving / WCS calibration for precise photo-to-sky alignment
- Additional DSO catalogs (Caldwell, Sharpless)
- Mobile-responsive touch controls
- Multi-language UI support

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [HYG Star Catalog](https://www.astronexus.com/hyg) — Stellar data
- [d3-celestial](https://github.com/ofrohn/d3-celestial) — Constellation line data
- [ModelScope](https://modelscope.cn) — Qwen-VL model hosting
- [Three.js](https://threejs.org) — WebGL rendering engine
