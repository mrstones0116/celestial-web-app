# 🌌 3D Celestial Sphere Visualization System

An immersive, physically-accurate 3D celestial sphere desktop application built with FastAPI, Three.js, and PyWebView. Renders the real-time sky for any observer location, time, and epoch.

## ✨ Features

### Core Rendering
- **Horizon Coordinate System (Alt-Az)**: Camera fixed at observer position; all celestial objects transformed via real-time horizon matrix driven by local sidereal time, latitude, and longitude
- **Realistic Sky Dome**: Vertex-colored sky dome with smooth twilight gradients (astronomical/nautical/civil twilight, purple transition) and east-west directional brightness during dawn/dusk
- **Semi-transparent Ground**: Below-horizon objects visible through translucent ground shell; labels always rendered above ground via depth-test override

### Solar System
- **Real-time Sun**: Meeus low-precision ephemeris; position, altitude, and sky color all driven by simulation time
- **Lunar Phases**: Dynamic terminator ellipse computed from Sun-Moon elongation; waxing/waning mirroring; phase updates every frame
- **7 Planets**: JPL Keplerian orbital elements (1800–2050 AD); precession-corrected to target epoch; real-time geocentric equatorial positions
- **Unified Labels**: Sun, Moon, and planet labels match star label style (size, position below object, FOV-locked scaling)
- **Solar System Search**: Type "Sun", "Moon", "Mars", etc. in search bar to focus camera on real-time position

### Star Catalog & Constellations
- **HYG Star Catalog**: ~119,000 stars with spectral coloring (O-B-A-F-G-K-M), layered rendering by magnitude, and glow enhancement
- **88 Constellation Lines**: Standard stick-figure data from d3-celestial GeoJSON (local file → online fallback → built-in simplified table); precession-corrected per epoch
- **Constellation Names**: Displayed at spherical geometric centroid of member stars (not brightest star)
- **Star Name Labels**: FOV-adaptive LOD — wider FOV shows only bright stars; zooming in progressively reveals fainter star names (up to mag 4.5)
- **Label Positioning**: All labels anchored below their parent object via sprite center offset

### Time & Epoch
- **Hong Kong Time (UTC+8)**: Precise to the second; flow/pause/manual adjustment
- **Observer Location**: Latitude/longitude input with preset cities (Hong Kong, Beijing, Tokyo, New York, London, Sydney, etc.) and GPS support
- **Epoch Time Travel**: Precession matrix (Lieske 1976) applied to stars, constellation lines, and planet positions; renders accurate sky for any year from ancient to future
- **Local Sidereal Time**: Computed from observer longitude; drives diurnal rotation and solar system positioning

### Interaction
- **Mouse Drag**: Rotate view (azimuth/elevation in horizon system)
- **Scroll Wheel**: FOV zoom (10°–110°); star sizes and label visibility adapt dynamically
- **Search**: Autocomplete search for stars and solar system bodies; click to smoothly animate camera to target
- **Display Toggles**: Independent controls for ground landscape, star labels, constellation lines, constellation names, and RA/Dec grid
- **Fullscreen Mode**: OS-level fullscreen toggle; red ✕ button to force-quit application

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Pandas, NumPy, Uvicorn |
| Frontend | Three.js, Canvas 2D, Vanilla JS |
| Desktop | PyWebView, PyInstaller |
| Data | HYG Database v4.1, d3-celestial constellation lines, JPL planetary elements |

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Modern web browser engine (Chromium via PyWebView)

### Installation
```bash
git clone https://github.com/mrstones0116/celestial-web-app.git
cd celestial-web-app

python -m venv astro_env
# Windows:
astro_env\Scripts\activate
# macOS/Linux:
source astro_env/bin/activate

pip install -r backend/requirements.txt
pip install pywebview pyinstaller
```

### Run in Development Mode
```bash
python main.py
```
The app launches in fullscreen. The launcher auto-selects an available port (starting from 8000) and waits for server readiness before opening the window.

### Build Desktop Executable
```bash
pyinstaller --noconfirm --onedir --windowed --name "CelestialApp_Final" \
  --add-data "frontend;frontend" \
  --add-data "backend;backend" \
  --paths backend \
  --hidden-import=server \
  --hidden-import=data_loader \
  --hidden-import=pandas \
  --hidden-import=numpy \
  --hidden-import=fastapi.middleware.cors \
  --hidden-import=uvicorn.logging \
  --hidden-import=uvicorn.loops \
  --hidden-import=uvicorn.loops.auto \
  --hidden-import=uvicorn.protocols \
  --hidden-import=uvicorn.protocols.http \
  --hidden-import=uvicorn.protocols.http.auto \
  --hidden-import=uvicorn.lifespan \
  --hidden-import=uvicorn.lifespan.on \
  --collect-all pandas \
  --collect-all numpy \
  main.py
```
Executable output: `dist/CelestialApp_Final/`

## 🎮 Controls

| Action | Effect |
|--------|--------|
| ☰ / ◀ | Toggle left control drawer |
| 📊 / ▶ | Toggle right data drawer |
| ⛶ | Enter/exit OS fullscreen |
| ✕ (red) | Force quit application |
| Mouse drag | Rotate view (horizon coordinates) |
| Scroll wheel | Zoom FOV (10°–110°); adjusts star sizes and label density |
| Double click | Reset view to default |
| Search box | Type star or planet name → autocomplete → click to focus |
| Time panel | Flow/pause, ±hour/day/year buttons, datetime picker |
| Location panel | Lat/lon input, city presets, GPS |
| Display toggles | Ground / Star labels / Constellation lines / Constellation names / RA-Dec grid |

## 📁 Project Structure
```
celestial_web_app/
├── backend/
│   ├── server.py              # FastAPI backend (renamed from main.py to avoid circular import)
│   ├── data_loader.py         # HYG data processing
│   └── requirements.txt
├── frontend/
│   ├── index.html             # Fullscreen immersive layout with drawers and HUD
│   ├── css/style.css          # Dark theme, drawer animations, toggle styles
│   ├── data/
│   │   └── constellations.lines.json  # 88-constellation GeoJSON (optional local cache)
│   └── js/
│       ├── app.js             # Main logic, UI bindings, relative API paths
│       ├── scene3d.js         # Three.js renderer (horizon coords, solar system, sky dome)
│       ├── chart2d.js         # 2D RA-Dec chart
│       ├── time.js            # Time system, observer location, epoch/precession, LST
│       └── search.js          # Star + solar system body search with autocomplete
├── main.py                    # Desktop launcher (auto port, fullscreen, readiness check)
└── README.md
```

## 🔭 Accuracy Notes

| Component | Method | Accuracy |
|-----------|--------|----------|
| Sun position | Meeus low-precision | ~0.01° |
| Moon position | Meeus truncated lunar theory | ~0.3° |
| Moon phase | Sun-Moon elongation + terminator ellipse | Visual accuracy |
| Planet positions | JPL Keplerian elements (1800–2050) | <1 arcmin within range |
| Precession | Lieske 1976 (IAU 1976) | Valid ±several millennia |
| Star positions | HYG v4.1 J2000 + precession correction | Catalog accuracy |
| Sky color | Altitude-driven multi-stop gradient with smoothstep | Perceptual match |

## 📄 License

MIT License
