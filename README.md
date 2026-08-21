
# 🌌 3D Celestial Sphere Visualization Web Application

An interactive 3D celestial sphere visualization web application based on the HYG star catalog.

## Stack

| layer | Technology |
|------|------|
| backend | FastAPI, Pandas, NumPy |
| frontend | Three.js, Canvas 2D, Vanilla JS |
| data | [HYG Database v4.1](https://github.com/astronexus/HYG-Database) |

## Function

- 🌐 3D Celestial Sphere Rendering (WebGL)

- 🔭 FOV Scaling (Telescope Effect, Camera Fixed at the Center of the Celestial Sphere)

- ⭐ Layered Rendering by Magnitude + Circular Star Textures

- 📊 2D Right Ascension-Declination Coordinates

- 🏛️ Constellation Statistics & Brightest Star Table

- 🎨 Spectral Type Color Mapping (O-B-A-F-G-K-M)

## Start

### Backend
```bash
cd backend
python -m venv astro_env
astro_env\Scripts\activate    # Windows
pip install -r requirements.txt
python main.py                # http://localhost:8000
```

### Frontend
```bash
cd frontend
python -m http.server 3000    # http://localhost:3000
```

## Structure
```
celestial_web_app/
├── backend/
│   ├── main.py            # FastAPI entrance
│   ├── data_loader.py     # HYG data processing
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── css/style.css
    └── js/
        ├── app.js         # main logics
        ├── scene3d.js     # Three.js 3D rendering
        └── chart2d.js     # 2D chart
```

## Data Source
[HYG Database](https://github.com/astronexus/HYG-Database) - It contains information such as right ascension, declination, magnitude, spectral type, and distance of stars visible to the naked eye (mag < 6).
```

Then submit the following:

```bash
git add README.md .gitignore
git commit -m "docs: add README and .gitignore"
git push
```

---

## ⚠️ Notice

| Problem | Solution |
|------|----------|
| The presence of spaces in the path caused the git command to fail. | Always enclose paths in double quotes |
| Password required when sending push notifications | Use SSH instead or configure [Personal Access Token](https://github.com/settings/tokens)|
| I accidentally uploaded `astro_env/` | After deleting, push again: `git rm -r --cached backend/astro_env && git commit -m "chore: Remove virtual environment" && git push`|
| Want to keep both Streamlit and other versions? | Simply place `celestial_web_app.py` in the root directory or a subdirectory of `streamlit/` and commit them together. |
