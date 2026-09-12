/**
 * scene3d.js - Three.js 3D 天球渲染（地平坐标系 Alt-Az）
 * 相机固定观测者位置；horizonGroup 矩阵 M(时间,纬度,经度) 把赤道坐标转到地平坐标
 * 东=+X, 天顶=+Y, 北=-Z；地平圈/NESW 标记固定不随时间转
 */

// ===== 行星轨道根数（JPL 近似表 1800-2050 AD）：[值, 每世纪变化率] =====
const PLANET_ELEMENTS = {
  Mercury:{a:[0.38709927,0.00000037],e:[0.20563593,0.00001906],I:[7.00497902,-0.00594749],L:[252.25032350,149472.67411175],w:[77.45779628,0.16047689],O:[48.33076593,-0.12534081]},
  Venus:  {a:[0.72333566,0.00000390],e:[0.00677672,-0.00004107],I:[3.39467605,-0.00078890],L:[181.97909950,58517.81538729],w:[131.60246718,0.00268329],O:[76.67984255,-0.27769418]},
  EMB:    {a:[1.00000261,0.00000562],e:[0.01671123,-0.00004392],I:[-0.00001531,-0.01294668],L:[100.46457166,35999.37244981],w:[102.93768193,0.32327364],O:[0.0,0.0]},
  Mars:   {a:[1.52371034,0.00001847],e:[0.09339410,0.00007882],I:[1.84969142,-0.00813131],L:[-4.55343205,19140.30268499],w:[-23.94362959,0.44441088],O:[49.55953891,-0.29257343]},
  Jupiter:{a:[5.20288700,-0.00011607],e:[0.04838624,-0.00013253],I:[1.30439695,-0.00183714],L:[34.39644051,3034.74612775],w:[14.72847983,0.21252668],O:[100.47390909,0.20469106]},
  Saturn: {a:[9.53667594,-0.00125060],e:[0.05386179,-0.00050991],I:[2.48599187,0.00193609],L:[49.95424423,1222.49362201],w:[92.59887831,-0.41897216],O:[113.66242448,-0.28867794]},
  Uranus: {a:[19.18916464,-0.00196176],e:[0.04725744,-0.00004397],I:[0.77263783,-0.00242939],L:[313.23810451,428.48202785],w:[170.95427630,0.40805281],O:[74.01692503,0.04240589]},
  Neptune:{a:[30.06992276,0.00026291],e:[0.00859048,0.00005105],I:[1.77004347,0.00035372],L:[-55.12002969,218.45945325],w:[44.96476227,-0.32241464],O:[131.78422574,-0.00508664]}
};
const PLANET_DISPLAY = {
  Mercury:{color:0x9c8e82,label:'Mercury'}, Venus:{color:0xe8cda2,label:'Venus'},
  Mars:{color:0xd1603d,label:'Mars'},       Jupiter:{color:0xd8a56a,label:'Jupiter'},
  Saturn:{color:0xe3c985,label:'Saturn'},   Uranus:{color:0x8fd1d8,label:'Uranus'},
  Neptune:{color:0x5b7fd4,label:'Neptune'}, Moon:{color:0xdddddd,label:'Moon'}
};

class CelestialScene3D {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.scene = null; this.camera = null; this.renderer = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        this.starData = []; this.starLayers = []; this.labels = [];
        this.animationId = null;
        this.circleTexture = this._createCircleTexture();
        this.fovDefault = 60; this.fovMin = 4; this.fovMax = 110; this.fovStep = 3;
        this.theta = Math.PI / 2;   // 地平系方位朝向
        this.phi = Math.PI / 2;     // 地平系天顶角
        this.rotateSpeed = 0.003;
        this.isDragging = false; this.lastMouseX = 0; this.lastMouseY = 0;this._mouseDownX = 0; this._mouseDownY = 0;
        this._focusAnim = null;
        this.constellationLines = null;
        this._labelsVisible = true;
        this._linesVisible = true;
        this.gridGroup = null;
        this._gridVisible = true;
        this.constNameLabels = [];
        this.sunGroup = null;
        this.sunLayers = null;   // { core, inner, outer }
        this.moonGroup = null;
        this._sunAltDeg = -90;   // 太阳地平高度（度），供白天判定
        this.moonLayers = null;  // { core, inner, outer, label }
        this.moonPhaseCanvas = null;
        this.moonPhaseCtx = null;
        this.moonPhaseTexture = null;
        this._lastMoonPhase = -1;
        this._sunLambda = 0;    // 太阳黄经（弧度）
        this._moonLambda = 0;   // 月球黄经（弧度）
        this.labelPool = [];        // { sprite, mag } 星名标签池
        this._magLimit = 2.5;       // 当前显示名字的最暗星等
        this._labelTexCache = {};   // 文字纹理缓存（避免重建 canvas）
        this._constNamesVisible = true;
        this.SPECTRAL_COLORS = {
            'O': 0x9bb0ff, 'B': 0xaabfff, 'A': 0xcad7ff, 'F': 0xf8f7ff,
            'G': 0xfff4ea, 'K': 0xffd2a1, 'M': 0xffcc6f, 'Other': 0xaaaaaa
        };
    }

    _createCircleTexture() {
        const size = 64;
        const canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        const ctx = canvas.getContext('2d');
        const g = ctx.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
        g.addColorStop(0, 'rgba(255,255,255,1.0)');
        g.addColorStop(0.4, 'rgba(255,255,255,0.8)');
        g.addColorStop(0.7, 'rgba(255,255,255,0.3)');
        g.addColorStop(1, 'rgba(255,255,255,0.0)');
        ctx.fillStyle = g; ctx.fillRect(0, 0, size, size);
        const tex = new THREE.CanvasTexture(canvas);
        tex.needsUpdate = true;
        return tex;
    }

    init() {
        const width  = this.container.clientWidth  || window.innerWidth;
        const height = this.container.clientHeight || window.innerHeight;
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x000000);
        this.camera = new THREE.PerspectiveCamera(this.fovDefault, width / height, 0.01, 100);
        this.camera.position.set(0, 0, 0);
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);

        // 地平变换组（矩阵 M 每帧更新，GPU 做变换，零逐星计算）
        this.horizonGroup = new THREE.Group();
        this.horizonGroup.matrixAutoUpdate = false;
        this.scene.add(this.horizonGroup);
        // 赤道坐标子组（星星/赤道网格/标注）
        this.skyGroup = new THREE.Group();
        this.gridGroup = new THREE.Group();
        this.skyGroup.add(this.gridGroup);
        this.horizonGroup.add(this.skyGroup);
        // 地平固定组（地平圈/NESW，不随时间转）
        this.horizonFixedGroup = new THREE.Group();
        this.scene.add(this.horizonFixedGroup);

        this._setupMouseControls();
        this.addGrid();
        this.addHorizon();
        this._createSunSprites();
        this._createMoonSprites();
        this._createSkyDome();
        this._createSolarSystem();
        this._updateCameraDirection();
        window.addEventListener('resize', () => this.onResize());
        this.animate();
    }

    _setupMouseControls() {
        const canvas = this.renderer.domElement;
        canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.lastMouseX = e.clientX; this.lastMouseY = e.clientY;
            this._mouseDownX = e.clientX; this._mouseDownY = e.clientY;
            this._focusAnim = null;
            canvas.style.cursor = 'grabbing';
        });
        canvas.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;   // 已移除悬浮提示，改为点击显示
            const dx = e.clientX - this.lastMouseX;
            const dy = e.clientY - this.lastMouseY;
            this.theta += dx * this.rotateSpeed;
            this.phi   -= dy * this.rotateSpeed;
            this.phi = Math.max(0.01, Math.min(Math.PI - 0.01, this.phi));
            this.lastMouseX = e.clientX; this.lastMouseY = e.clientY;
            this._updateCameraDirection();
            this._applyLabelLOD();
        });
        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            canvas.style.cursor = 'grab';
        });
        // 点击检测：区分"点击"与"拖拽后释放"
        canvas.addEventListener('click', (e) => {
            const dx = e.clientX - this._mouseDownX;
            const dy = e.clientY - this._mouseDownY;
            if (Math.sqrt(dx*dx + dy*dy) > 5) return;   // 拖拽，不触发
            this._onClickRaycast(e);
        });
        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const dir = e.deltaY > 0 ? 1 : -1;
            this.camera.fov = Math.max(this.fovMin,
                Math.min(this.fovMax, this.camera.fov + dir * this.fovStep));
            this.camera.updateProjectionMatrix();
            this._updateStarSizes();
            this._applyLabelLOD();
            const ind = document.getElementById('fov-indicator');
            if (ind) { ind.textContent = `FOV: ${this.camera.fov.toFixed(0)}°`; ind.style.display = 'block'; }
        }, { passive: false });
        canvas.addEventListener('dblclick', () => {
            this.camera.fov = this.fovDefault;
            this.camera.updateProjectionMatrix();
            this.theta = Math.PI / 2; this.phi = Math.PI / 2;
            this._updateCameraDirection();
        });
        canvas.style.cursor = 'grab';
    }

    _updateCameraDirection() {
        const lookTarget = new THREE.Vector3(
            Math.sin(this.phi) * Math.cos(-this.theta),
            Math.cos(this.phi),
            Math.sin(this.phi) * Math.sin(-this.theta)
        );
        this.camera.lookAt(lookTarget);
    }

    _updateStarSizes() {
        const starScaleFactor = this.fovDefault / this.camera.fov;
        for (const layer of this.starLayers) {
            if (layer.userData.baseSize) {
                layer.material.size = layer.userData.baseSize * starScaleFactor;
            }
        }
        
        // FOV < 50° 时，文字标签停止放大（锁定在 FOV=50 时的屏幕大小）
        const textScaleFactor = this.camera.fov < 50 ? (this.camera.fov / 50) : 1.0;
        
        const updateSpriteScale = (sprite) => {
            if (sprite && sprite.userData.baseScale) {
                const bs = sprite.userData.baseScale;
                sprite.scale.set(bs.x * textScaleFactor, bs.y * textScaleFactor, 1);
            }
        };

        if (this.labelPool) this.labelPool.forEach(L => updateSpriteScale(L.sprite));
        if (this.constNameLabels) this.constNameLabels.forEach(sp => updateSpriteScale(sp));
        if (this.solarBodies) Object.values(this.solarBodies).forEach(b => updateSpriteScale(b.label));
        if (this.moonLayers) updateSpriteScale(this.moonLayers.label);
        if (this.sunLayers) updateSpriteScale(this.sunLayers.label);
    }

    // ===== 地平变换矩阵 M（赤道场景坐标 e → 地平场景坐标 h）=====
    _updateHorizonMatrix(lst, lat) {
        this._updateSunPosition();
        this._updateSolarSystemPositions();
        const sL = Math.sin(lst), cL = Math.cos(lst);
        const sP = Math.sin(lat), cP = Math.cos(lat);
        this.horizonGroup.matrix.set(
            -sL,      0,    -cL,      0,
             cP * cL, sP,   -cP * sL, 0,
             sP * cL, -cP,  -sP * sL, 0,
             0, 0, 0, 1
        );
        this.horizonGroup.matrixWorldNeedsUpdate = true;
    }

    _updateRaycast(event) {
        const rect = this.container.getBoundingClientRect();
        this.mouse.x =  ((event.clientX - rect.left) / rect.width)  * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        this.raycaster.params.Points.threshold = 0.02;
        const tooltip = document.getElementById('tooltip');
        let closestStar = null, closestDist = Infinity;
        for (const layer of this.starLayers) {
            if (!layer.geometry.attributes.position || layer.material.opacity < 0.5) continue;
            const hits = this.raycaster.intersectObject(layer);
            if (hits.length > 0 && hits[0].distance < closestDist) {
                closestDist = hits[0].distance;
                closestStar = this._findNearestStar(layer.worldToLocal(hits[0].point.clone()));
            }
        }
        if (closestStar) {
            tooltip.innerHTML = `
                <div class="star-name">${closestStar.name}</div>
                <div class="star-detail">
                    星座: ${closestStar.constellation}<br>
                    赤经: ${closestStar.ra_hours.toFixed(3)}h<br>
                    赤纬: ${closestStar.dec.toFixed(2)}°<br>
                    视星等: ${closestStar.mag}<br>
                    光谱: ${closestStar.spect}<br>
                    距离: ${closestStar.dist_ly} ly
                </div>`;
            tooltip.style.display = 'block';
            tooltip.style.left = (event.clientX + 15) + 'px';
            tooltip.style.top  = (event.clientY + 15) + 'px';
        } else {
            tooltip.style.display = 'none';
        }
    }

    // ===== 点击检测：恒星 + 太阳系天体，显示详细信息 =====
    _onClickRaycast(event) {
        const rect = this.container.getBoundingClientRect();
        this.mouse.x =  ((event.clientX - rect.left) / rect.width)  * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        this.raycaster.params.Points.threshold = 0.02;

        // 1. 检测恒星
        let hitStar = null, hitStarDist = Infinity;
        for (const layer of this.starLayers) {
            if (!layer.geometry.attributes.position || layer.material.opacity < 0.5) continue;
            const hits = this.raycaster.intersectObject(layer);
            if (hits.length > 0 && hits[0].distance < hitStarDist) {
                hitStarDist = hits[0].distance;
                hitStar = this._findNearestStar(layer.worldToLocal(hits[0].point.clone()));
            }
        }

        // 2. 检测太阳系天体（角度匹配）
        let hitBody = null, hitBodyAngle = Infinity;
        const checkBody = (obj, type, name) => {
            if (!obj || !obj.visible) return;
            const wp = obj.getWorldPosition(new THREE.Vector3());
            const toObj = wp.clone().sub(this.raycaster.ray.origin).normalize();
            const ang = this.raycaster.ray.direction.angleTo(toObj);
            if (ang < 0.05 && ang < hitBodyAngle) {
                hitBodyAngle = ang;
                hitBody = { type, name, worldPos: wp };
            }
        };
        if (this.sunGroup) checkBody(this.sunGroup, 'sun', 'Sun');
        if (this.moonGroup) checkBody(this.moonGroup, 'moon', 'Moon');
        if (this.solarBodies) {
            for (const key of Object.keys(this.solarBodies)) {
                checkBody(this.solarBodies[key].dot, 'planet', PLANET_DISPLAY[key].label);
            }
        }

        // 3. 优先显示太阳系天体（更近），否则恒星
        if (hitBody) {
            const { az, alt } = this._calcAzAlt(hitBody.worldPos);
            this._showInfoPanel({
                type: hitBody.type, name: hitBody.name,
                az, alt
            });
        } else if (hitStar) {
            this.showStarInfo(hitStar);   // 与搜索走同一方法
        }else {
            this._hideInfoPanel(); // 点击空白处关闭面板
        }
    }

    // ===== 由地平场景坐标计算方位角/高度角 =====
    _calcAzAlt(worldPos) {
        const v = worldPos.clone().normalize();
        const alt = Math.asin(THREE.MathUtils.clamp(v.y, -1, 1));
        let az = Math.atan2(v.x, -v.z); // 北 = -Z
        if (az < 0) az += 2 * Math.PI;
        return { az: az * 180 / Math.PI, alt: alt * 180 / Math.PI };
    }

    // ===== 信息面板 =====
    _ensureInfoPanelStyle() {
        if (document.getElementById('info-panel-style')) return;
        const style = document.createElement('style');
        style.id = 'info-panel-style';
        style.textContent = `
            #info-panel {
                position: fixed; top: 60px; right: 20px; width: 280px;
                background: rgba(20,25,40,0.95); border: 1px solid #4A90E2;
                border-radius: 8px; padding: 16px; font-size: 0.85rem; color: #ccc;
                z-index: 1001; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            }
            #info-panel h4 { color: #4A90E2; margin: 0 0 10px 0; font-size: 1.1rem; }
            #info-panel .info-row { margin: 4px 0; }
            #info-panel .info-label { color: #888; }
            #info-panel .info-close {
                position: absolute; top: 8px; right: 12px; cursor: pointer;
                color: #888; font-size: 1rem;
            }
            #info-panel .info-close:hover { color: #fff; }
            #info-panel .fav-btn {
                margin-top: 12px; padding: 6px 12px; background: #4A90E2;
                color: white; border: none; border-radius: 4px; cursor: pointer;
            }
            #info-panel .fav-btn:hover { background: #357ABD; }
            #info-panel .fav-btn.faved { background: #27ae60; }
        `;
        document.head.appendChild(style);
    }

    _showInfoPanel(info) {
        this._ensureInfoPanelStyle();
        let panel = document.getElementById('info-panel');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'info-panel';
            document.body.appendChild(panel);
        }
        const azStr = info.az.toFixed(2) + '°';
        const altStr = info.alt.toFixed(2) + '°';
        let html = `<span class="info-close" onclick="window.celestialScene._hideInfoPanel()">✕</span>`;
        html += `<h4>${info.name}</h4>`;
        html += `<div class="info-row"><span class="info-label">类型:</span> ${
            info.type === 'star' ? '恒星' : info.type === 'sun' ? '太阳' : info.type === 'moon' ? '月球' : '行星'
        }</div>`;
        if (info.type === 'star') {
            if (info.constellation) html += `<div class="info-row"><span class="info-label">星座:</span> ${info.constellation}</div>`;
            if (info.ra_hours != null) html += `<div class="info-row"><span class="info-label">赤经:</span> ${info.ra_hours.toFixed(3)}h</div>`;
            if (info.dec != null) html += `<div class="info-row"><span class="info-label">赤纬:</span> ${info.dec.toFixed(2)}°</div>`;
            if (info.mag != null) html += `<div class="info-row"><span class="info-label">视星等:</span> ${info.mag}</div>`;
            if (info.spect) html += `<div class="info-row"><span class="info-label">光谱:</span> ${info.spect}</div>`;
            if (info.dist_ly != null) html += `<div class="info-row"><span class="info-label">距离:</span> ${info.dist_ly} ly</div>`;
        }
        html += `<div class="info-row"><span class="info-label">方位角 Az:</span> ${azStr}</div>`;
        html += `<div class="info-row"><span class="info-label">高度角 Alt:</span> ${altStr}</div>`;
        if (info.type === 'star' && info.starData && info.name && info.name !== '(unnamed)') {
            const isFaved = window.isFavorite && window.isFavorite(info.name);
            html += `<button class="fav-btn ${isFaved ? 'faved' : ''}" data-star='${JSON.stringify(info.starData).replace(/'/g, "&#39;")}'>${isFaved ? '✓ 已收藏' : '☆ 收藏'}</button>`;
        }
        panel.innerHTML = html;
        panel.style.display = 'block';
        const favBtn = panel.querySelector('.fav-btn');
        if (favBtn) {
            favBtn.onclick = () => {
                const star = JSON.parse(favBtn.dataset.star);
                if (window.toggleFavorite) window.toggleFavorite(star);
                const nowFaved = window.isFavorite && window.isFavorite(info.name);
                favBtn.textContent = nowFaved ? '✓ 已收藏' : '☆ 收藏';
                favBtn.classList.toggle('faved', nowFaved);
            };
        }
    }

    _hideInfoPanel() {
        const panel = document.getElementById('info-panel');
        if (panel) panel.style.display = 'none';
    }

    _findNearestStar(point) {
        let best = null, bestDist = Infinity;
        for (const star of this.starData) {
            const dx = star.x - point.x;
            const dy = star.z - point.y;
            const dz = -star.y - point.z;
            const dist = dx * dx + dy * dy + dz * dz;
            if (dist < bestDist) { bestDist = dist; best = star; }
        }
        return bestDist < 0.001 ? best : null;
    }

    // ===== 赤道网格（随 M 转到地平视图）=====
    addGrid() {
        // 天球赤道（青色）
        const eqPts = [];
        for (let i = 0; i <= 128; i++) {
            const a = (i / 128) * Math.PI * 2;
            eqPts.push(new THREE.Vector3(Math.cos(a), 0, Math.sin(a)));
        }
        this.gridGroup.add(new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(eqPts),
            new THREE.LineBasicMaterial({ color: 0x00ffff, transparent: true, opacity: 0.4 })));
        
        // 赤纬圈（灰色）
        for (let dec = -60; dec <= 60; dec += 30) {
            if (dec === 0) continue;
            const r = Math.cos(dec * Math.PI / 180), h = Math.sin(dec * Math.PI / 180);
            const pts = [];
            for (let i = 0; i <= 64; i++) {
                const a = (i / 64) * Math.PI * 2;
                pts.push(new THREE.Vector3(r * Math.cos(a), h, r * Math.sin(a)));
            }
            this.gridGroup.add(new THREE.Line(
                new THREE.BufferGeometry().setFromPoints(pts),
                new THREE.LineBasicMaterial({ color: 0x444444, transparent: true, opacity: 0.3 })));
        }
        
        // 赤经线（绿色）
        for (let ra = 0; ra < 24; ra += 3) {
            const raRad = -(ra * 15 * Math.PI) / 180;
            const pts = [];
            for (let i = 0; i <= 50; i++) {
                const d = -Math.PI / 2 + (Math.PI * i) / 50;
                pts.push(new THREE.Vector3(
                    Math.cos(d) * Math.cos(raRad), Math.sin(d), Math.cos(d) * Math.sin(raRad)));
            }
            this.gridGroup.add(new THREE.Line(
                new THREE.BufferGeometry().setFromPoints(pts),
                new THREE.LineBasicMaterial({ color: 0x00ff00, transparent: true, opacity: 0.2 })));
        }
    }

    // ===== 地平圈 + 方位标记（固定不随时间转）=====
    addHorizon() {
        const pts = [];
        for (let i = 0; i <= 128; i++) {
            const a = (i / 128) * Math.PI * 2;
            pts.push(new THREE.Vector3(Math.cos(a), 0, Math.sin(a)));
        }
        this.horizonFixedGroup.add(new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(pts),
            new THREE.LineBasicMaterial({ color: 0xff8844, transparent: true, opacity: 0.6 })));
        const marks = [
            ['N', 0, 0, -1.08, 0xff4444],
            ['E', 1.08, 0, 0, 0xffffff],
            ['S', 0, 0, 1.08, 0xffffff],
            ['W', -1.08, 0, 0, 0xffffff]
        ];
        for (const [t, x, y, z, c] of marks) {
            const sp = this.createTextSprite(t, c);
            sp.position.set(x, y, z);
            sp.scale.set(0.1, 0.05, 1);
            this.horizonFixedGroup.add(sp);
        }
        // 地面：下半球壳，从球内看内壁，遮住地平线以下的星
        const groundGeo = new THREE.SphereGeometry(0.98, 32, 16, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2);
        const groundMat = new THREE.MeshBasicMaterial({ 
            color: 0x0c1210, 
            side: THREE.BackSide, 
            transparent: true, 
            opacity: 0.35   // 半透明地景
        });
        this.horizonFixedGroup.add(new THREE.Mesh(groundGeo, groundMat));
    }

    updateStars(stars, brightStars) {
        // ===== 彻底剔除星表太阳 Sol：只保留实时计算的 Sun =====
        stars = stars.filter(s => (s.name || '').toLowerCase() !== 'sol');
        if (brightStars) brightStars = brightStars.filter(s => (s.name || '').toLowerCase() !== 'sol');

        // Epoch 岁差：保存原始 J2000 坐标并按渲染历元变换
        this._rawStars = stars;
        this._rawBright = brightStars || [];
        if (window.timeManager && window.timeManager.precessionMatrix) {
            const P = window.timeManager.precessionMatrix(window.timeManager.getEpochYear());
            stars = stars.map(s => this._applyPrecession(s, P));
            if (brightStars) brightStars = brightStars.map(s => this._applyPrecession(s, P));
        }

        // 清除旧对象
        this.starLayers.forEach(l => this.skyGroup.remove(l));
        this.labels.forEach(l => this.skyGroup.remove(l));
        this.labels = []; this.starLayers = [];
        this.starData = stars;   // 不含 Sol
        if (!stars.length) return;
        const layers = [
            { maxMag: 1.0, size: 10, opacity: 1.0 },
            { maxMag: 2.5, size: 8, opacity: 0.95 },
            { maxMag: 4.0, size: 6, opacity: 0.85 },
            { maxMag: 6.0, size: 4, opacity: 0.7 }
        ];
        let prev = -Infinity;
        for (const layer of layers) {
            const ls = stars.filter(s => s.mag > prev && s.mag <= layer.maxMag);
            prev = layer.maxMag;
            if (!ls.length) continue;
            const pos = new Float32Array(ls.length * 3);
            const col = new Float32Array(ls.length * 3);
            ls.forEach((s, i) => {
                pos[i*3] = s.x; pos[i*3+1] = s.z; pos[i*3+2] = -s.y;
                const c = new THREE.Color(this.SPECTRAL_COLORS[s.spect_class] || 0xaaaaaa);
                col[i*3] = c.r; col[i*3+1] = c.g; col[i*3+2] = c.b;
            });
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
            geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
            const mat = new THREE.PointsMaterial({
                size: layer.size, map: this.circleTexture, alphaTest: 0.01,
                vertexColors: true, transparent: true, opacity: layer.opacity,
                sizeAttenuation: false, depthWrite: false
            });
            const p = new THREE.Points(geo, mat);
            p.userData.baseSize = layer.size;
            this.skyGroup.add(p);
            this.starLayers.push(p);
        }
        const gs = stars.filter(s => s.mag <= 2.5);
        if (gs.length) {
            const gp = new Float32Array(gs.length * 3);
            const gc = new Float32Array(gs.length * 3);
            gs.forEach((s, i) => {
                gp[i*3] = s.x; gp[i*3+1] = s.z; gp[i*3+2] = -s.y;
                const c = new THREE.Color(this.SPECTRAL_COLORS[s.spect_class] || 0xaaaaaa);
                gc[i*3] = c.r; gc[i*3+1] = c.g; gc[i*3+2] = c.b;
            });
            const gg = new THREE.BufferGeometry();
            gg.setAttribute('position', new THREE.BufferAttribute(gp, 3));
            gg.setAttribute('color', new THREE.BufferAttribute(gc, 3));
            const gm = new THREE.PointsMaterial({
                size: 18, map: this.circleTexture, alphaTest: 0.01, vertexColors: true,
                transparent: true, opacity: 0.15, sizeAttenuation: false, depthWrite: false
            });
            const gpts = new THREE.Points(gg, gm);
            gpts.userData.baseSize = 18;
            this.skyGroup.add(gpts);
            this.starLayers.push(gpts);
        }
        // ===== 星名标签池（mag<=4.5 且有专有名），按 FOV 动态显示，名字在星点正下方 =====
        if (this.labelPool) {
            this.labelPool.forEach(L => {
                this.skyGroup.remove(L.sprite);
                L.sprite.material.dispose();      // texture 走缓存，不 dispose
            });
        }
        this.labelPool = [];
        const poolStars = stars.filter(s => s.name && s.name.trim() && s.mag <= 4.5);
        for (const s of poolStars) {
            const tex = this._getLabelTexture(s.name, 30);
            const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
                map: tex, transparent: true, depthWrite: false
            }));
            sprite.scale.set(0.18, 0.045, 1);
            sprite.center.set(0.5, 1.0);          // 锚点顶边之上 → 文字落在星点正下方
            sprite.userData.baseScale = { x: 0.18, y: 0.045 };
            sprite.position.set(s.x * 1.02, s.z * 1.02, -s.y * 1.02);
            sprite.visible = false;
            this.skyGroup.add(sprite);
            this.labelPool.push({ sprite, mag: s.mag });
        }
        this.labels = this.labelPool.map(L => L.sprite);   // 兼容旧引用
        this._applyLabelLOD();
        this.updateConstellationLines();
        this.updateConstellationNames();
    }

    createTextSprite(text, colorHex = 0xffffff, fontSize = 28) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 256; canvas.height = 64;
        ctx.font = `Bold ${fontSize}px Arial`;
        ctx.fillStyle = '#' + colorHex.toString(16).padStart(6, '0');
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, 128, 32);
        const texture = new THREE.CanvasTexture(canvas);
        const material = new THREE.SpriteMaterial({
            map: texture, transparent: true, depthWrite: false
        });
        const sprite = new THREE.Sprite(material);
        sprite.scale.set(0.18, 0.045, 1);   // 星名加大
        return sprite;
    }

    // 文字纹理缓存：同名同字号复用，避免每次 updateStars 重画 canvas
    _getLabelTexture(text, fontSize) {
        const key = text + '_' + fontSize;
        if (this._labelTexCache[key]) return this._labelTexCache[key];
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 256; canvas.height = 64;
        ctx.font = `Bold ${fontSize}px Arial`;
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, 128, 32);
        const tex = new THREE.CanvasTexture(canvas);
        this._labelTexCache[key] = tex;
        return tex;
    }

    // 星名可见深度：FOV 越小（放大）→ 显示越暗的星名
    _computeMagLimit() {
        const t = (this.fovDefault - this.camera.fov) / (this.fovDefault - this.fovMin);
        return THREE.MathUtils.clamp(2.5 + t * 2.0, 2.5, 4.5);
    }

    _applyLabelLOD() {
        this._magLimit = this._computeMagLimit();
        if (!this.labelPool) return;
        for (const L of this.labelPool) {
            L.sprite.visible = this._labelsVisible && (L.mag <= this._magLimit);
        }
    }

    _applyPrecession(s, P) {
        const x = P[0]*s.x + P[1]*s.y + P[2]*s.z;
        const y = P[3]*s.x + P[4]*s.y + P[5]*s.z;
        const z = P[6]*s.x + P[7]*s.y + P[8]*s.z;
        const dec = Math.asin(Math.max(-1, Math.min(1, z))) * 180 / Math.PI;
        let raH = Math.atan2(y, x) * 12 / Math.PI;
        if (raH < 0) raH += 24;
        return Object.assign({}, s, { x, y, z, dec: +dec.toFixed(2), ra_hours: +raH.toFixed(4) });
    }

    updateConstellationLines() {
        if (this.constellationLines) {
            this.skyGroup.remove(this.constellationLines);
            this.constellationLines.geometry.dispose();
            this.constellationLines.material.dispose();
            this.constellationLines = null;
        }
        const pts = [];
        if (window.__constLineSegs && window.__constLineSegs.length) {
            // 88 星座标准 stick-figure（d3-celestial GeoJSON），并叠加岁差
            const P = (window.timeManager && window.timeManager.precessionMatrix)
                ? window.timeManager.precessionMatrix(window.timeManager.getEpochYear()) : null;
            const ap = v => P ? [
                P[0]*v[0] + P[1]*v[1] + P[2]*v[2],
                P[3]*v[0] + P[4]*v[1] + P[5]*v[2],
                P[6]*v[0] + P[7]*v[1] + P[8]*v[2]
            ] : v;
            for (const s of window.__constLineSegs) {
                const a = ap([s[0], s[1], s[2]]);
                const b = ap([s[3], s[4], s[5]]);
                pts.push(a[0], a[2], -a[1], b[0], b[2], -b[1]);
            }
        } else {
            // 回退：内置星名简表（数据文件与网络都不可用时）
            const byName = {};
            for (const s of this.starData) if (s.name) byName[s.name] = s;
            for (const con of Object.keys(CONSTELLATION_LINES)) {
                for (const pair of CONSTELLATION_LINES[con]) {
                    const sa = byName[pair[0]], sb = byName[pair[1]];
                    if (!sa || !sb) continue;
                    pts.push(sa.x, sa.z, -sa.y, sb.x, sb.z, -sb.y);
                }
            }
        }
        if (!pts.length) return;
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pts), 3));
        const mat = new THREE.LineBasicMaterial({ color: 0x4a7dff, transparent: true, opacity: 0.5 });
        this.constellationLines = new THREE.LineSegments(geo, mat);
        this.constellationLines.visible = this._linesVisible;
        this.skyGroup.add(this.constellationLines);
    }

    // ===== 加载 88 星座连线：本地优先 → 在线回退 → 内置简表，全程非阻塞 =====
    loadConstellationLines() {
        const LOCAL  = 'data/constellations.lines.json';
        const REMOTE = 'https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/constellations.lines.json';
        const fetchTO = (url, ms) => {
            const ctrl = new AbortController();
            const t = setTimeout(() => ctrl.abort(), ms);
            return fetch(url, { signal: ctrl.signal }).finally(() => clearTimeout(t));
        };
        fetchTO(LOCAL, 3000)
            .then(r => { if (!r.ok) throw 0; return r.json(); })
            .catch(() => fetchTO(REMOTE, 8000).then(r => { if (!r.ok) throw 0; return r.json(); }))
            .then(gj => {
                window.__constLineSegs = this._parseLineGeoJSON(gj);
                this.updateConstellationLines();
                this.updateConstellationNames();   // ★ 新增：连线就绪后连带刷新星座名称
            })
            .catch(() => { /* 均失败 → 保持内置简表回退 */ });
    }

    // GeoJSON MultiLineString([ra°, dec°]) → 3D 单位向量线段
    _parseLineGeoJSON(gj) {
        const segs = [];
        const vec = (p) => {
            const ra = p[0] * Math.PI / 180, dec = p[1] * Math.PI / 180;
            return [Math.cos(dec) * Math.cos(ra), Math.cos(dec) * Math.sin(ra), Math.sin(dec)];
        };
        for (const f of (gj.features || [])) {
            const coords = f.geometry && f.geometry.coordinates;
            if (!coords) continue;
            for (const line of coords) {
                for (let i = 0; i < line.length - 1; i++) {
                    const a = vec(line[i]), b = vec(line[i + 1]);
                    segs.push([a[0], a[1], a[2], b[0], b[1], b[2]]);
                }
            }
        }
        return segs;
    }

    // ===== 星座天区名称：显示在该星座成员星的球面几何中心 =====
    updateConstellationNames() {
        this.constNameLabels.forEach(l => this.skyGroup.remove(l));
        this.constNameLabels = [];
        if (!this.starData.length) return;
        const acc = {};
        for (const s of this.starData) {
            const c = s.constellation;
            if (!c) continue;
            if (!acc[c]) acc[c] = { x: 0, y: 0, z: 0, n: 0 };
            acc[c].x += s.x; acc[c].y += s.y; acc[c].z += s.z; acc[c].n++;
        }
        for (const c of Object.keys(acc)) {
            const a = acc[c];
            if (!a.n) continue;
            let x = a.x / a.n, y = a.y / a.n, z = a.z / a.n;
            const len = Math.sqrt(x*x + y*y + z*z);
            if (len < 1e-6) continue;
            x /= len; y /= len; z /= len;
            const sp = this.createTextSprite(c, 0x88aaff, 34);
            sp.scale.set(0.28, 0.07, 1);
            sp.userData.baseScale = { x: 0.28, y: 0.07 };
            sp.position.set(x * 0.90, z * 0.90, -y * 0.90);
            sp.visible = this._constNamesVisible;
            this.skyGroup.add(sp);
            this.constNameLabels.push(sp);
        }
    }

    setConstNamesVisible(v) {
        this._constNamesVisible = v;
        this.constNameLabels.forEach(l => l.visible = v);
    }

    // ===== 显示开关 =====
    setGroundVisible(v) { if (this.horizonFixedGroup) this.horizonFixedGroup.visible = v; }
    setLabelsVisible(v) {
        this._labelsVisible = v;
        this._applyLabelLOD();
    }
    setLinesVisible(v)  { this._linesVisible = v; if (this.constellationLines) this.constellationLines.visible = v; }
    setGridVisible(v) { 
        this._gridVisible = v; 
        if (this.gridGroup) this.gridGroup.visible = v; 
    }

    refreshEpoch() {
        if (this._rawStars && this._rawStars.length) {
            this.updateStars(this._rawStars, this._rawBright);
            this._updateStarSizes();
        }
    }

    animate() {
        this.animationId = requestAnimationFrame(() => this.animate());
        // 地平变换：每帧更新全局矩阵 M（时间/经纬度变化自动生效）
        if (this.horizonGroup && window.timeManager) {
            const tm = window.timeManager;
            this._updateHorizonMatrix(tm.getLocalSiderealTime(), tm.latitude * Math.PI / 180);
        }
        if (this._focusAnim) {
            const a = this._focusAnim;
            const k = Math.min(1, (performance.now() - a.t0) / a.duration);
            const e = k < 0.5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2;
            this.theta = a.fromTheta + a.dTheta * e;
            this.phi   = a.fromPhi + (a.toPhi - a.fromPhi) * e;
            this._updateCameraDirection();
            if (k >= 1) this._focusAnim = null;
        }
        // 必须包含这两行：
        this._updateSunPosition();
        this._updateSolarSystemPositions();
        this.renderer.render(this.scene, this.camera);
    }

    onResize() {
        const w = this.container.clientWidth  || window.innerWidth;
        const h = this.container.clientHeight || window.innerHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }

    focusOnStar(star, duration = 1200) {
        if (!star) return;
        const e = new THREE.Vector3(star.x, star.z, -star.y);
        const w = e.applyMatrix4(this.horizonGroup.matrix);   // 赤道 → 地平
        const targetTheta = Math.atan2(-w.z, w.x);
        const targetPhi   = Math.acos(THREE.MathUtils.clamp(w.y, -1, 1));
        let dTheta = targetTheta - this.theta;
        while (dTheta >  Math.PI) dTheta -= Math.PI * 2;
        while (dTheta < -Math.PI) dTheta += Math.PI * 2;
        this._focusAnim = {
            t0: performance.now(), duration,
            fromTheta: this.theta, dTheta,
            fromPhi: this.phi, toPhi: targetPhi
        };
        this._flashHighlight(star);
    }

    // ===== 公开：显示恒星信息面板（供搜索/收藏调用，与点击完全一致）=====
    showStarInfo(star) {
        if (!star) return;
        const e = new THREE.Vector3(star.x, star.z, -star.y);
        const h = e.applyMatrix4(this.horizonGroup.matrix);   // 赤道 → 地平
        const { az, alt } = this._calcAzAlt(h);
        this._showInfoPanel({
            type: 'star', name: star.name || '(unnamed)',
            constellation: star.constellation,
            ra_hours: star.ra_hours, dec: star.dec,
            mag: star.mag, spect: star.spect, dist_ly: star.dist_ly,
            az, alt, starData: star
        });
    }

    // 供收藏夹点击时直接显示信息面板
    _onClickFocusStar(star) {
        const e = new THREE.Vector3(star.x, star.z, -star.y);
        const h = e.applyMatrix4(this.horizonGroup.matrix);
        const { az, alt } = this._calcAzAlt(h);
        this._showInfoPanel({
            type: 'star', name: star.name || '(unnamed)',
            constellation: star.constellation,
            ra_hours: star.ra_hours, dec: star.dec,
            mag: star.mag, spect: star.spect, dist_ly: star.dist_ly,
            az, alt, starData: star
        });
    }

    // ===== 聚焦太阳系天体（按名称取实时位置）=====
    focusOnSolarBody(name) {
        let pos = null;   // 场景坐标 (赤道场景坐标)
        if (name === 'Sun' && this.sunGroup) {
            pos = this.sunGroup.position;
        } else if (name === 'Moon' && this.moonGroup) {
            pos = this.moonGroup.position;
        } else if (this.solarBodies && this.solarBodies[name]) {
            pos = this.solarBodies[name].dot.position;
        }
        if (!pos) return;
         // 场景坐标 (x, z, -y) → 数学坐标 (x, y, z)，供 focusOnStar 使用
        const fakeStar = { x: pos.x, y: -pos.z, z: pos.y };
        this.focusOnStar(fakeStar);
     }
     
    _flashHighlight(star) {
        const mat = new THREE.SpriteMaterial({
            map: this.circleTexture, color: 0xffdd44,
            transparent: true, opacity: 0.95, depthWrite: false
        });
        const sp = new THREE.Sprite(mat);
        sp.position.set(star.x, star.z, -star.y);
        sp.scale.set(0.1, 0.1, 1);
        this.skyGroup.add(sp);
        const t0 = performance.now();
        const fade = () => {
            const k = (performance.now() - t0) / 2500;
            if (k >= 1) { this.skyGroup.remove(sp); mat.dispose(); return; }
            mat.opacity = 0.95 * (1 - k);
            requestAnimationFrame(fade);
        };
        fade();
    }

    _createSunSprites() {
        this.sunGroup = new THREE.Group();
        this.sunLayers = {};
        const layers = [
            { key: 'outer', size: 0.30, color: 0xffee88, opacity: 0.25 },
            { key: 'inner', size: 0.16, color: 0xffdd44, opacity: 0.50 },
            { key: 'core',  size: 0.05, color: 0xfff8e0, opacity: 1.00 }   // ← 大小同月亮(0.05)，暖黄白
        ];
        for (const L of layers) {
            const mat = new THREE.SpriteMaterial({
                map: this.circleTexture, color: L.color,
                transparent: true, opacity: L.opacity, depthWrite: false
            });
            const sp = new THREE.Sprite(mat);
            sp.scale.set(L.size, L.size, 1);
            this.sunGroup.add(sp);
            this.sunLayers[L.key] = sp;
        }
        this.skyGroup.add(this.sunGroup);
        // 太阳标签（与恒星一致：大小、正下方）
        const label = this.createTextSprite('Sun', 0xffdd88, 30);
        label.scale.set(0.18, 0.045, 1);
        label.userData.baseScale = { x: 0.18, y: 0.045 };
        label.center.set(0.5, 1.0);       // 文字在星点正下方
        label.position.set(0, 0, 0);      // 星点中心
        label.visible = true;
        this.sunGroup.add(label);
        this.sunLayers.label = label;
    }

    // ===== 月球：光晕面积同太阳 + 真实月相 =====
    _createMoonSprites() {
        this.moonGroup = new THREE.Group();
        this.moonLayers = {};
        // 月相动态纹理
        this.moonPhaseCanvas = document.createElement('canvas');
        this.moonPhaseCanvas.width = 128; this.moonPhaseCanvas.height = 128;
        this.moonPhaseCtx = this.moonPhaseCanvas.getContext('2d');
        this.moonPhaseTexture = new THREE.CanvasTexture(this.moonPhaseCanvas);
        this._drawMoonPhase(0.5);   // 初始满月占位
        // 光晕层（圆形，不随月相变形）
        const glowLayers = [
            { key: 'outer', size: 0.30, color: 0xdde4ee, opacity: 0.18 },
            { key: 'inner', size: 0.16, color: 0xe8eef6, opacity: 0.35 }
        ];
        for (const L of glowLayers) {
            const mat = new THREE.SpriteMaterial({ map: this.circleTexture, color: L.color, transparent: true, opacity: L.opacity, depthWrite: false });
            const sp = new THREE.Sprite(mat);
            sp.scale.set(L.size, L.size, 1);
            this.moonGroup.add(sp);
            this.moonLayers[L.key] = sp;
        }
        // 月盘：月相纹理
        const coreMat = new THREE.SpriteMaterial({ map: this.moonPhaseTexture, transparent: true, opacity: 1, depthWrite: false });
        const coreSp = new THREE.Sprite(coreMat);
        coreSp.scale.set(0.05, 0.05, 1);
        this.moonGroup.add(coreSp);
        this.moonLayers.core = coreSp;
        // 标签（与恒星一致）
        const label = this.createTextSprite('Moon', 0xdddddd, 30);
        label.scale.set(0.18, 0.045, 1);
        label.userData.baseScale = { x: 0.18, y: 0.045 };
        label.center.set(0.5, 1.0);       // 文字在星点正下方
        label.position.set(0, 0, 0);      // 星点中心
        this.moonGroup.add(label);
        this.moonLayers.label = label;
        this.skyGroup.add(this.moonGroup);   // ★★★ 关键：月亮必须挂进场景图，否则不显示
    }

    // ===== 绘制月相：phase∈[0,1)，0=新月 0.25=上弦 0.5=满月 0.75=下弦 =====
    _drawMoonPhase(phase) {
        const ctx = this.moonPhaseCtx;
        const S = 128, c = S / 2, R = S / 2 - 2;
        ctx.clearRect(0, 0, S, S);
        // 暗盘（含微弱地球反照）
        ctx.fillStyle = 'rgba(58,58,64,0.92)';
        ctx.beginPath(); ctx.arc(c, c, R, 0, Math.PI * 2); ctx.fill();
        const p = phase * 2 * Math.PI;
        const cosP = Math.cos(p);
        const waxing = phase < 0.5;      // 北半球：上弦右亮 / 下弦左亮
        ctx.save();
        ctx.translate(c, c);
        if (!waxing) ctx.scale(-1, 1);   // 下弦水平镜像 → 左亮
        // 亮区 = 亮侧半圆 ± terminator 半椭圆
        ctx.fillStyle = '#f2f2e6';
        ctx.beginPath();
        ctx.arc(0, 0, R, -Math.PI / 2, Math.PI / 2, false);   // 右半圆（顶→底）
        const rx = Math.abs(cosP) * R;
        if (rx > 0.5) {
            // crescent(cosP>0): 椭圆弯向亮侧(右)；gibbous(cosP<0): 弯向暗侧(左)
            ctx.ellipse(0, 0, rx, R, 0, Math.PI / 2, -Math.PI / 2, cosP > 0);
        } else {
            ctx.lineTo(0, -R);          // 弦月：terminator 为直线
        }
        ctx.closePath();
        ctx.fill();
        ctx.restore();
        this.moonPhaseTexture.needsUpdate = true;
    }

    // ===== 天空背景色：随太阳地平高度自然渐变（修复 RGB 插值发灰问题）=====
    _skyColorForAlt(alt) {
        const deg = alt * 180 / Math.PI;
        // 精心挑选的 stops，强制插入紫红色过渡，避免 RGB 插值产生“泥巴色”
        const stops = [
            [-18.0, new THREE.Color(0x020308)], // 天文黑夜：极暗蓝黑
            [-12.0, new THREE.Color(0x060b1c)], // 深空蓝
            [ -6.0, new THREE.Color(0x111833)], // 航海黄昏：深蓝
            [ -3.0, new THREE.Color(0x2a1b3d)], // 暮光：暗紫红 (关键过渡色！)
            [ -0.5, new THREE.Color(0x8a3020)], // 日落/日出瞬间：暗橙红
            [  1.0, new THREE.Color(0xd96a30)], // 地平线附近：亮橙红
            [  4.0, new THREE.Color(0xe09a55)], // 黄金时刻：金黄
            [ 10.0, new THREE.Color(0x9ecfef)],   // 白天：浅蓝
            [ 30.0, new THREE.Color(0x88c4e8)]    // 正午：浅蓝（略深）
        ];
        
        if (deg <= stops[0][0]) return stops[0][1].clone();
        if (deg >= stops[stops.length-1][0]) return stops[stops.length-1][1].clone();
        
        for (let i = 0; i < stops.length - 1; i++) {
            if (deg >= stops[i][0] && deg <= stops[i+1][0]) {
                const t = (deg - stops[i][0]) / (stops[i+1][0] - stops[i][0]);
                // 使用 smoothstep 让过渡更柔和，符合人眼对光线变化的感知
                const smoothT = t * t * (3 - 2 * t); 
                return new THREE.Color().lerpColors(stops[i][1], stops[i+1][1], smoothT);
            }
        }
        return new THREE.Color(0x000000);
    }

    // ===== 天空穹顶：顶点色实现黄昏/黎明"自东向西"明暗渐变 =====
    _createSkyDome() {
        const geo = new THREE.SphereGeometry(60, 24, 12);
        const count = geo.attributes.position.count;
        geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
        const mat = new THREE.MeshBasicMaterial({
            vertexColors: true, side: THREE.BackSide, depthWrite: false
        });
        this.skyDome = new THREE.Mesh(geo, mat);
        this.skyDome.renderOrder = -1;
        this.scene.add(this.skyDome);   // 地平固定系，不随天球旋转
    }

    _updateSkyDome(sunDirScene, altDeg) {
        if (!this.skyDome) return;
        const posAttr = this.skyDome.geometry.attributes.position;
        const colAttr = this.skyDome.geometry.attributes.color;
        // 夜晚：全黑
        if (altDeg < -18) {
            for (let i = 0; i < posAttr.count; i++) colAttr.setXYZ(i, 0, 0, 0);
            colAttr.needsUpdate = true;
            return;
        }
        // 黄昏/黎明权重：alt 在 [-18, 10] 之间方位渐变明显，白天≈0（均匀浅蓝）
        const tw = THREE.MathUtils.clamp(1 - Math.abs(altDeg + 4) / 14, 0, 1);
        const brightSide = this._skyColorForAlt((altDeg + 7) * Math.PI / 180);  // 朝太阳方位
        const darkSide   = this._skyColorForAlt((altDeg - 9) * Math.PI / 180);  // 背太阳方位
        const v = new THREE.Vector3();
        const c = new THREE.Color();
        for (let i = 0; i < posAttr.count; i++) {
            v.fromBufferAttribute(posAttr, i).normalize();
            const facing = (v.dot(sunDirScene) + 1) / 2;   // 1=朝太阳, 0=背向
            const t = THREE.MathUtils.clamp(0.5 + (facing - 0.5) * tw, 0, 1);
            c.lerpColors(darkSide, brightSide, t);
            colAttr.setXYZ(i, c.r, c.g, c.b);
        }
        colAttr.needsUpdate = true;
    }

    _createCrossTexture() {
        const size = 128, c = size / 2;
        const canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        const ctx = canvas.getContext('2d');
        let g = ctx.createLinearGradient(0, c, size, c);          // 水平芒
        g.addColorStop(0, 'rgba(255,244,192,0)');
        g.addColorStop(0.5, 'rgba(255,244,192,0.9)');
        g.addColorStop(1, 'rgba(255,244,192,0)');
        ctx.fillStyle = g; ctx.fillRect(0, c - 1.5, size, 3);
        g = ctx.createLinearGradient(c, 0, c, size);              // 垂直芒
        g.addColorStop(0, 'rgba(255,244,192,0)');
        g.addColorStop(0.5, 'rgba(255,244,192,0.9)');
        g.addColorStop(1, 'rgba(255,244,192,0)');
        ctx.fillStyle = g; ctx.fillRect(c - 1.5, 0, 3, size);
        const tex = new THREE.CanvasTexture(canvas);
        tex.needsUpdate = true;
        return tex;
    }

    // 每帧按模拟时间更新太阳视位置、天空颜色、光晕及 Sol 同步
    _updateSunPosition() {
        if (!this.sunGroup || !window.timeManager) return;
        const tm = window.timeManager;
        const d = (tm.getSimMs() - 946728000000) / 86400000;
        
        // Meeus 低精度太阳视位置
        const L = (280.460 + 0.9856474 * d) * Math.PI / 180;
        const g = (357.528 + 0.9856003 * d) * Math.PI / 180;
        const lambda = L + (1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * Math.PI / 180;
        this._sunLambda = lambda;   // 记录太阳黄经，供月相计算
        const eps = (23.439 - 0.0000004 * d) * Math.PI / 180;
        const ra  = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda));
        const dec = Math.asin(Math.sin(eps) * Math.sin(lambda));
        
        const x = Math.cos(dec) * Math.cos(ra);
        const y = Math.cos(dec) * Math.sin(ra);
        const z = Math.sin(dec);
        this.sunGroup.position.set(x, z, -y);

        // ===== 计算太阳地平高度并更新天空颜色 =====
        const lat = tm.latitude * Math.PI / 180;
        const lst = tm.getLocalSiderealTime();
        const H = lst - ra; 
        const sinAlt = Math.sin(lat)*Math.sin(dec) + Math.cos(lat)*Math.cos(dec)*Math.cos(H);
        const alt = Math.asin(THREE.MathUtils.clamp(sinAlt, -1, 1));
        
        // 驱动天空背景色渐变
        this.scene.background = this._skyColorForAlt(alt);
        
        const deg = alt * 180 / Math.PI;
        this._sunAltDeg = deg;
        // 太阳在地平场景系的方向 → 驱动天空穹顶方位渐变
        const sunDirScene = new THREE.Vector3(x, z, -y)
            .applyMatrix4(this.horizonGroup.matrix).normalize();
        this._updateSkyDome(sunDirScene, deg);
        
        // 太阳落下时平滑隐藏光晕
        const k = THREE.MathUtils.clamp((deg + 3) / 3, 0, 1);
        if (this.sunLayers) {
            if (this.sunLayers.outer) { this.sunLayers.outer.material.opacity = 0.25 * k; this.sunLayers.outer.visible = k > 0.01; }
            if (this.sunLayers.inner) { this.sunLayers.inner.material.opacity = 0.50 * k; this.sunLayers.inner.visible = k > 0.01; }
        }
        if (this.solSprite) this.solSprite.position.set(x, z, -y);
    }

    // ===== 太阳系天体：开普勒历表 + 月球理论 =====
    _keplerSolve(M, e) {
        let E = M + e * Math.sin(M) * (1 + e * Math.cos(M));
        for (let i = 0; i < 8; i++) {
            const dE = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
            E -= dE;
            if (Math.abs(dE) < 1e-8) break;
        }
        return E;
    }
    _planetHeliocentric(key, T) {
        const el = PLANET_ELEMENTS[key];
        const a = el.a[0] + el.a[1]*T, e = el.e[0] + el.e[1]*T;
        const I = (el.I[0]+el.I[1]*T)*Math.PI/180, L = (el.L[0]+el.L[1]*T)*Math.PI/180;
        const w = (el.w[0]+el.w[1]*T)*Math.PI/180, O = (el.O[0]+el.O[1]*T)*Math.PI/180;
        const argP = w - O;
        const M = (L - w) % (2*Math.PI);
        const E = this._keplerSolve(M, e);
        const xp = a*(Math.cos(E)-e), yp = a*Math.sqrt(1-e*e)*Math.sin(E);
        const cw=Math.cos(argP), sw=Math.sin(argP), cO=Math.cos(O), sO=Math.sin(O), cI=Math.cos(I), sI=Math.sin(I);
        return [
            (cw*cO - sw*sO*cI)*xp + (-sw*cO - cw*sO*cI)*yp,
            (cw*sO + sw*cO*cI)*xp + (-sw*sO + cw*cO*cI)*yp,
            (sw*sI)*xp + (cw*sI)*yp
        ];
    }
    _planetGeocentricEquJ2000(key, T) {
        const hp = this._planetHeliocentric(key, T);
        const he = this._planetHeliocentric('EMB', T);
        const g = [hp[0]-he[0], hp[1]-he[1], hp[2]-he[2]];
        const eps = 23.4392911 * Math.PI/180;   // J2000 黄赤交角
        const ce=Math.cos(eps), se=Math.sin(eps);
        const eq = [g[0], g[1]*ce - g[2]*se, g[1]*se + g[2]*ce];
        const len = Math.hypot(eq[0], eq[1], eq[2]);
        return [eq[0]/len, eq[1]/len, eq[2]/len];
    }
    _moonEquatorialOfDate(d) {
        const D2R = Math.PI/180;
        const L = (218.316 + 13.176396*d)*D2R;
        const M = (134.963 + 13.064993*d)*D2R;
        const F = (93.272 + 13.229350*d)*D2R;
        const D = (297.850 + 12.190749*d)*D2R;
        const Ms = (357.529 + 0.98560028*d)*D2R;
        const lam = L + (6.289*Math.sin(M) + 1.274*Math.sin(2*D-M) + 0.658*Math.sin(2*D)
                      + 0.214*Math.sin(2*M) - 0.186*Math.sin(Ms) - 0.114*Math.sin(2*F))*D2R;
        this._moonLambda = lam;     // 记录月球黄经，供月相计算
        const bet = (5.128*Math.sin(F) + 0.281*Math.sin(M+F) - 0.278*Math.sin(M-F)
                      - 0.173*Math.sin(2*D-F))*D2R;
        const eps = (23.4392911 - 0.0130042*(d/36525))*D2R;   // of-date 黄赤交角
        const cb = Math.cos(bet);
        return [
            cb*Math.cos(lam),
            cb*Math.sin(lam)*Math.cos(eps) - Math.sin(bet)*Math.sin(eps),
            cb*Math.sin(lam)*Math.sin(eps) + Math.sin(bet)*Math.cos(eps)
        ];
    }
    _getPrecessionMatrix(year) {
        if (this._precCache && this._precCache.year === year) return this._precCache.P;
        const P = window.timeManager.precessionMatrix(year);
        this._precCache = { year, P };
        return P;
    }
    _createSolarSystem() {
        this.planetsGroup = new THREE.Group();
        this.skyGroup.add(this.planetsGroup);
        this.solarBodies = {};
        for (const key of Object.keys(PLANET_DISPLAY)) {
            if (key === 'Moon') continue;   // 月球改用独立 moonGroup 渲染
            const info = PLANET_DISPLAY[key];
            const dot = new THREE.Sprite(new THREE.SpriteMaterial({
                map: this.circleTexture, color: info.color,
                transparent: true, opacity: 1, depthWrite: false
            }));
            dot.scale.set(0.03, 0.03, 1);
            const label = this.createTextSprite(info.label, info.color, 30);
            label.scale.set(0.18, 0.045, 1);
            label.userData.baseScale = { x: 0.18, y: 0.045 };
            label.center.set(0.5, 1.0);       // 文字在星点正下方
            this.planetsGroup.add(dot);        // ★ 关键：行星点加入场景
            this.planetsGroup.add(label);      // ★ 关键：行星标签加入场景
            this.solarBodies[key] = { dot, label };  // ★ 关键：记录引用供每帧更新
        }
    }
    _updateSolarSystemPositions() {
        if (!this.planetsGroup || !window.timeManager) return;
        const tm = window.timeManager;
        const d = (tm.getSimMs() - 946728000000) / 86400000;
        const T = d / 36525;
        const P = this._getPrecessionMatrix(tm.getEpochYear());
        const applyP = v => [
            P[0]*v[0]+P[1]*v[1]+P[2]*v[2],
            P[3]*v[0]+P[4]*v[1]+P[5]*v[2],
            P[6]*v[0]+P[7]*v[1]+P[8]*v[2]
        ];
        const lat = tm.latitude * Math.PI / 180;
        const lst = tm.getLocalSiderealTime();
        // 白天因子：太阳在地平上→1（光辉被蓝天淹没），夜→0；±2° 平滑过渡
        const kDay = THREE.MathUtils.clamp((this._sunAltDeg + 2) / 4, 0, 1);

        for (const key of Object.keys(PLANET_DISPLAY)) {
            if (key === 'Sol') continue;
            const eq = (key === 'Moon')
                ? this._moonEquatorialOfDate(d)
                : applyP(this._planetGeocentricEquJ2000(key, T));

            // 该天体自身的地平高度
            const ra  = Math.atan2(eq[1], eq[0]);
            const dec = Math.asin(THREE.MathUtils.clamp(eq[2], -1, 1));
            const H   = lst - ra;
            const sinAlt = Math.sin(lat)*Math.sin(dec) + Math.cos(lat)*Math.cos(dec)*Math.cos(H);
            const altDeg = Math.asin(THREE.MathUtils.clamp(sinAlt, -1, 1)) * 180 / Math.PI;
            // 地上因子：地平下→0（被地球遮挡），±1° 平滑过渡
            const kAbove = THREE.MathUtils.clamp((altDeg + 1) / 2, 0, 1);

            if (key === 'Moon') {
                if (this.moonGroup) this.moonGroup.position.set(eq[0], eq[2], -eq[1]);
                // ===== 月相：距角 D = λ月 − λ日 =====
                let D = (this._moonLambda || 0) - (this._sunLambda || 0);
                D = ((D % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
                const phase = D / (2 * Math.PI);   // 0=新月 0.5=满月
                const waxFlip = (phase < 0.5) !== (this._lastMoonPhase < 0.5);
                if (this._lastMoonPhase < 0 || waxFlip || Math.abs(phase - this._lastMoonPhase) > 0.002) {
                    this._drawMoonPhase(phase);
                    this._lastMoonPhase = phase;
                }
                if (this.moonLayers) {
                    const L = this.moonLayers;
                    if (L.core)  { L.core.visible  = kAbove > 0.01; L.core.material.opacity  = 1.0 * kAbove; }
                    // 名字始终显示，不受落下限制
                    if (L.label) { L.label.visible = true; L.label.material.opacity = 1.0; } 
                    const glowK = kAbove * (1 - kDay);
                    if (L.outer) { L.outer.visible = glowK > 0.01; L.outer.material.opacity = 0.18 * glowK; }
                    if (L.inner) { L.inner.visible = glowK > 0.01; L.inner.material.opacity = 0.35 * glowK; }
                }
                continue;
            }

            const body = this.solarBodies[key];
            if (!body) continue;
            body.dot.position.set(eq[0], eq[2], -eq[1]);
            body.label.position.set(eq[0], eq[2], -eq[1]);
            
            const vis = kAbove * (1 - kDay);
            body.dot.visible   = vis > 0.01;
            body.dot.material.opacity = 1.0 * vis;
            // 名字始终显示，不受落下和白天限制
            body.label.visible = true; 
            body.label.material.opacity = 1.0;
        }
    }
    destroy() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.renderer) this.renderer.dispose();
    }
}