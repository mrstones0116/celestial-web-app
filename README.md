# 🌌 3D Celestial Sphere Visualization System

An interactive, immersive 3D celestial sphere visualization desktop application based on the HYG star catalog. Built with FastAPI, Three.js, and PyWebView.

## ✨ Features

- **Immersive Fullscreen Mode**: Starfield fills the entire window by default; side panels are slide-out drawers.
- **3D Celestial Sphere**: WebGL rendering with camera fixed at the center of the celestial sphere.
- **FOV Scaling**: Mouse wheel controls field of view (telescope effect), with dynamic star size adjustment.
- **Layered Rendering**: Stars rendered in layers by magnitude with circular textures and spectral color mapping (O-B-A-F-G-K-M).
- **Star Search**: Dynamic autocomplete search bar; click to auto-focus and highlight the target star.
- **Time System**: Hong Kong time (UTC+8) accurate to the second; supports natural flow, pause, and manual time adjustment. Drives diurnal rotation via Local Sidereal Time (LST).
- **2D RA-Dec Chart**: Canvas-based equatorial coordinate visualization.
- **Constellation Statistics**: Real-time stats and brightest star tables.

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Pandas, NumPy |
| Frontend | Three.js, Canvas 2D, Vanilla JS |
| Desktop | PyWebView, PyInstaller |
| Data | HYG Database v4.1 |

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Node.js (optional, for frontend tooling)

### Installation
```bash
# Clone the repository
git clone https://github.com/mrstones0116/celestial-web-app.git
cd celestial-web-app

# Create and activate virtual environment
python -m venv astro_env
# Windows:
astro_env\Scripts\activate
# macOS/Linux:
source astro_env/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
pip install pywebview pyinstaller
```

### Run in Development Mode
```bash
python main.py
```
The app will launch in fullscreen mode. The local server auto-selects an available port (starting from 8000).

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
The executable will be generated in `dist/CelestialApp_Final/`.

## 🎮 Controls

- **☰ / 📊 Buttons**: Toggle left control menu and right data panel.
- **⛶ Button**: Enter/exit OS-level fullscreen.
- **Mouse Drag**: Rotate the celestial sphere (left/right and up/down).
- **Mouse Wheel**: Zoom in/out (adjust FOV).
- **Double Click**: Reset view to default.
- **Search Bar**: Type star name (e.g., "Sirius") and click Search to focus.
- **Time Panel**: Toggle flow/pause, adjust time manually, or jump to specific dates.

## 📁 Project Structure
```
celestial_web_app/
├── backend/
│   ├── server.py          # FastAPI backend (renamed from main.py)
│   ├── data_loader.py     # HYG data processing
│   └── requirements.txt
├── frontend/
│   ├── index.html         # Immersive fullscreen layout
│   ├── css/style.css      # Drawer UI styles
│   └── js/
│       ├── app.js         # Main logic (relative API paths)
│       ├── scene3d.js     # Three.js 3D rendering
│       ├── chart2d.js     # 2D RA-Dec chart
│       ├── time.js        # Time system & LST calculation
│       └── search.js      # Star search & focus
├── main.py                # Desktop launcher (auto port, fullscreen)
└── README.md
```

## 📄 License
MIT License
```
