/**
 * scene3d.js - Three.js 3D 天球渲染
 * 相机固定天球中心；滚轮 FOV 缩放；拖拽旋转；时间系统驱动周日旋转
 */
class CelestialScene3D {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        this.starData = [];
        this.starLayers = [];
        this.labels = [];
        this.animationId = null;
        this.circleTexture = this._createCircleTexture();

        this.fovDefault = 60;
        this.fovMin = 10;
        this.fovMax = 110;
        this.fovStep = 3;
        this.theta = Math.PI / 2;
        this.phi = Math.PI / 2;
        this.rotateSpeed = 0.003;
        this.isDragging = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;
        this._focusAnim = null;

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
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, size, size);
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

        this.skyGroup = new THREE.Group();
        this.scene.add(this.skyGroup);

        this._setupMouseControls();
        this.addGrid();
        this._updateCameraDirection();
        window.addEventListener('resize', () => this.onResize());
        this.animate();
    }

    _setupMouseControls() {
        const canvas = this.renderer.domElement;
        canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;
            this._focusAnim = null;
            canvas.style.cursor = 'grabbing';
        });
        canvas.addEventListener('mousemove', (e) => {
            this._updateRaycast(e);
            if (!this.isDragging) return;
            const dx = e.clientX - this.lastMouseX;
            const dy = e.clientY - this.lastMouseY;
            this.theta += dx * this.rotateSpeed;
            this.phi   -= dy * this.rotateSpeed;
            this.phi = Math.max(0.01, Math.min(Math.PI - 0.01, this.phi));
            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;
            this._updateCameraDirection();
        });
        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            canvas.style.cursor = 'grab';
        });
        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const dir = e.deltaY > 0 ? 1 : -1;
            this.camera.fov = Math.max(this.fovMin,
                Math.min(this.fovMax, this.camera.fov + dir * this.fovStep));
            this.camera.updateProjectionMatrix();
            this._updateStarSizes();
            const ind = document.getElementById('fov-indicator');
            if (ind) {
                ind.textContent = `FOV: ${this.camera.fov.toFixed(0)}°`;
                ind.style.display = 'block';
            }
        }, { passive: false });
        canvas.addEventListener('dblclick', () => {
            this.camera.fov = this.fovDefault;
            this.camera.updateProjectionMatrix();
            this.theta = Math.PI / 2;
            this.phi = Math.PI / 2;
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
        const f = this.fovDefault / this.camera.fov;
        for (const layer of this.starLayers) {
            if (layer.userData.baseSize) layer.material.size = layer.userData.baseSize * f;
        }
    }

    _updateRaycast(event) {
        const rect = this.container.getBoundingClientRect();
        this.mouse.x =  ((event.clientX - rect.left) / rect.width)  * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        this.raycaster.params.Points.threshold = 0.02;
        const tooltip = document.getElementById('tooltip');
        let closestStar = null;
        let closestDist = Infinity;
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

    _findNearestStar(point) {
        let best = null;
        let bestDist = Infinity;
        for (const star of this.starData) {
            const dx = star.x - point.x;
            const dy = star.z - point.y;
            const dz = -star.y - point.z;
            const dist = dx * dx + dy * dy + dz * dz;
            if (dist < bestDist) { bestDist = dist; best = star; }
        }
        return bestDist < 0.001 ? best : null;
    }

    addGrid() {
        const eqPts = [];
        for (let i = 0; i <= 128; i++) {
            const a = (i / 128) * Math.PI * 2;
            eqPts.push(new THREE.Vector3(Math.cos(a), 0, Math.sin(a)));
        }
        this.skyGroup.add(new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(eqPts),
            new THREE.LineBasicMaterial({ color: 0x00ffff, transparent: true, opacity: 0.4 })));
        for (let dec = -60; dec <= 60; dec += 30) {
            if (dec === 0) continue;
            const r = Math.cos(dec * Math.PI / 180), h = Math.sin(dec * Math.PI / 180);
            const pts = [];
            for (let i = 0; i <= 64; i++) {
                const a = (i / 64) * Math.PI * 2;
                pts.push(new THREE.Vector3(r * Math.cos(a), h, r * Math.sin(a)));
            }
            this.skyGroup.add(new THREE.Line(
                new THREE.BufferGeometry().setFromPoints(pts),
                new THREE.LineBasicMaterial({ color: 0x444444, transparent: true, opacity: 0.3 })));
        }
        for (let ra = 0; ra < 24; ra += 3) {
            const raRad = -(ra * 15 * Math.PI) / 180;
            const pts = [];
            for (let i = 0; i <= 50; i++) {
                const d = -Math.PI / 2 + (Math.PI * i) / 50;
                pts.push(new THREE.Vector3(
                    Math.cos(d) * Math.cos(raRad), Math.sin(d), Math.cos(d) * Math.sin(raRad)));
            }
            this.skyGroup.add(new THREE.Line(
                new THREE.BufferGeometry().setFromPoints(pts),
                new THREE.LineBasicMaterial({ color: 0x00ff00, transparent: true, opacity: 0.2 })));
        }
    }

    updateStars(stars, brightStars) {
        this.starLayers.forEach(l => this.skyGroup.remove(l));
        this.labels.forEach(l => this.skyGroup.remove(l));
        this.labels = [];
        this.starLayers = [];
        this.starData = stars;
        if (!stars.length) return;

        const layers = [
            { maxMag: 1.0, size: 7, opacity: 1.0 },
            { maxMag: 2.5, size: 5, opacity: 0.95 },
            { maxMag: 4.0, size: 3, opacity: 0.85 },
            { maxMag: 6.0, size: 2, opacity: 0.7 }
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
            const pts = new THREE.Points(geo, mat);
            pts.userData.baseSize = layer.size;
            this.skyGroup.add(pts);
            this.starLayers.push(pts);
        }
        // 亮星光辉层
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
                size: 12, map: this.circleTexture, alphaTest: 0.01, vertexColors: true,
                transparent: true, opacity: 0.15, sizeAttenuation: false, depthWrite: false
            });
            const gpts = new THREE.Points(gg, gm);
            gpts.userData.baseSize = 12;
            this.skyGroup.add(gpts);
            this.starLayers.push(gpts);
        }
        // 亮星标注
        if (brightStars) {
            brightStars.forEach(s => {
                const sp = this.createTextSprite(s.name);
                sp.position.set(s.x * 1.05, s.z * 1.05, -s.y * 1.05);
                this.skyGroup.add(sp);
                this.labels.push(sp);
            });
        }
    }

    createTextSprite(text) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 256; canvas.height = 64;
        ctx.font = 'Bold 20px Arial';
        ctx.fillStyle = 'white';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, 128, 32);
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
            map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false
        }));
        sprite.scale.set(0.12, 0.03, 1);
        return sprite;
    }

    animate() {
        this.animationId = requestAnimationFrame(() => this.animate());
        if (this.skyGroup && window.timeManager) {
            this.skyGroup.rotation.y = -window.timeManager.getLocalSiderealTime();
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
        const rho = this.skyGroup ? this.skyGroup.rotation.y : 0;
        const p = new THREE.Vector3(star.x, star.z, -star.y)
            .applyAxisAngle(new THREE.Vector3(0, 1, 0), rho);
        const targetTheta = Math.atan2(-p.z, p.x);
        const targetPhi   = Math.acos(THREE.MathUtils.clamp(p.y, -1, 1));
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

    destroy() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.renderer) this.renderer.dispose();
    }
}