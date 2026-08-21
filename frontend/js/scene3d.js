/**
 * Three.js 3D天球渲染模块
 * 相机固定在天球中心，滚轮控制FOV实现缩放
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
        this.labels = [];
        this.animationId = null;
        this.circleTexture = this._createCircleTexture();

        // ===== 视角控制参数 =====
        this.fovDefault = 60;       // 默认FOV
        this.fovMin = 10;           // 最小FOV（最大放大，望远镜效果）
        this.fovMax = 110;          // 最大FOV（最大缩小，广角效果）
        this.fovStep = 3;           // 每次滚轮变化量

        // 球坐标控制相机朝向（theta=水平旋转, phi=垂直旋转）
        this.theta = Math.PI / 2;   // 初始朝向
        this.phi = Math.PI / 2;     // π/2 = 水平方向
        this.rotateSpeed = 0.003;   // 拖拽旋转灵敏度

        // 鼠标状态
        this.isDragging = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;

        this.SPECTRAL_COLORS = {
            'O': 0x9bb0ff,
            'B': 0xaabfff,
            'A': 0xcad7ff,
            'F': 0xf8f7ff,
            'G': 0xfff4ea,
            'K': 0xffd2a1,
            'M': 0xffcc6f,
            'Other': 0xaaaaaa
        };
    }

    // ✅ _createCircleTexture 放在这里（constructor 之后、init 之前）
    /**
     * 用 Canvas 动态生成圆形纹理
     */
    _createCircleTexture() {
        const size = 64;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');

        const gradient = ctx.createRadialGradient(
            size / 2, size / 2, 0,
            size / 2, size / 2, size / 2
        );
        gradient.addColorStop(0, 'rgba(255, 255, 255, 1.0)');
        gradient.addColorStop(0.4, 'rgba(255, 255, 255, 0.8)');
        gradient.addColorStop(0.7, 'rgba(255, 255, 255, 0.3)');
        gradient.addColorStop(1, 'rgba(255, 255, 255, 0.0)');

        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, size, size);

        const texture = new THREE.CanvasTexture(canvas);
        texture.needsUpdate = true;
        return texture;
    }

    init() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;

        // 场景
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x000000);

        // ===== 相机：固定在天球中心 =====
        this.camera = new THREE.PerspectiveCamera(
            this.fovDefault,      // FOV
            width / height,       // 宽高比
            0.01,                 // 近裁剪面（非常小，因为相机在原点）
            100                   // 远裁剪面
        );
        this.camera.position.set(0, 0, 0);  // 始终在天球中心！

        // 渲染器
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);

        // ===== 不使用 OrbitControls，自己实现交互 =====
        this._setupMouseControls();

        // 添加天球网格
        this.addGrid();

        // 初始相机朝向
        this._updateCameraDirection();

        // 窗口大小变化
        window.addEventListener('resize', () => this.onResize());

        // 开始渲染循环
        this.animate();
    }

    // ===== 鼠标交互 =====
    _setupMouseControls() {
        const canvas = this.renderer.domElement;

        // 鼠标按下 → 开始拖拽旋转
        canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;
            canvas.style.cursor = 'grabbing';
        });

        // 鼠标移动 → 旋转视角
        canvas.addEventListener('mousemove', (e) => {
            // 更新射线检测（悬停提示）
            this._updateRaycast(e);

            if (!this.isDragging) return;

            const dx = e.clientX - this.lastMouseX;
            const dy = e.clientY - this.lastMouseY;

            // 水平拖拽 → 改变 theta（左右看）
            this.theta -= dx * this.rotateSpeed;

            // 垂直拖拽 → 改变 phi（上下看）
            this.phi -= dy * this.rotateSpeed;
            // 限制 phi 范围，防止翻转
            this.phi = Math.max(0.01, Math.min(Math.PI - 0.01, this.phi));

            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;

            this._updateCameraDirection();
        });

        // 鼠标松开 → 停止拖拽
        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            canvas.style.cursor = 'grab';
        });

        // ===== 滚轮 → FOV缩放（核心修改！）=====
        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();

            const direction = e.deltaY > 0 ? 1 : -1;
            this.camera.fov += direction * this.fovStep;
            this.camera.fov = Math.max(this.fovMin, Math.min(this.fovMax, this.camera.fov));
            this.camera.updateProjectionMatrix();

            // ✅ 新增：星星大小跟随FOV变化
            this._updateStarSizes();

            // 更新FOV指示器
            const indicator = document.getElementById('fov-indicator');
            if (indicator) {
                indicator.textContent = `FOV: ${this.camera.fov.toFixed(0)}°`;
                indicator.style.display = 'block';
            }
        }, { passive: false });

        // 双击 → 重置视角
        canvas.addEventListener('dblclick', () => {
            this.camera.fov = this.fovDefault;
            this.camera.updateProjectionMatrix();
            this.theta = Math.PI / 2;
            this.phi = Math.PI / 2;
            this._updateCameraDirection();
        });

        // 初始光标样式
        canvas.style.cursor = 'grab';
    }

    // 根据球坐标更新相机朝向
    _updateCameraDirection() {
        const lookTarget = new THREE.Vector3(
            Math.sin(this.phi) * Math.cos(this.theta),
            Math.cos(this.phi),
            Math.sin(this.phi) * Math.sin(this.theta)
        );
        this.camera.lookAt(lookTarget);
    }

    _updateStarSizes() {
        const scaleFactor = this.fovDefault / this.camera.fov;

        for (const layer of this.starLayers) {
            if (layer.userData.baseSize) {
                layer.material.size = layer.userData.baseSize * scaleFactor;
            }
        }
    }
    _updateRaycast(event) {
        const rect = this.container.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);
        this.raycaster.params.Points.threshold = 0.02;

        const tooltip = document.getElementById('tooltip');

        // 遍历所有星星层进行检测
        let closestStar = null;
        let closestDist = Infinity;

        if (this.starLayers && this.starLayers.length > 0) {
            for (const layer of this.starLayers) {
                // 跳过光辉层（没有对应 starData）
                if (!layer.geometry.attributes.position || 
                    layer.material.opacity < 0.5) continue;

                const intersects = this.raycaster.intersectObject(layer);
                if (intersects.length > 0 && intersects[0].distance < closestDist) {
                    closestDist = intersects[0].distance;
                    const idx = intersects[0].index;
                    // 注意：这里的 index 是层内索引，需要在 starData 中找到对应星星
                    // 简化方案：直接用全局 starData 做距离匹配
                    closestStar = this._findNearestStar(intersects[0].point);
                }
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
                    距离: ${closestStar.dist_ly} ly<br>
                    <span style="color:#666;font-size:0.7rem">FOV: ${this.camera.fov.toFixed(0)}°</span>
                </div>
            `;
            tooltip.style.display = 'block';
            tooltip.style.left = (event.clientX + 15) + 'px';
            tooltip.style.top = (event.clientY + 15) + 'px';
        } else {
            tooltip.style.display = 'none';
        }
    }

    // 新增辅助方法：根据3D坐标查找最近的星星
    _findNearestStar(point) {
        let best = null;
        let bestDist = Infinity;
        for (const star of this.starData) {
            const dx = star.x - point.x;
            const dy = star.z - point.y;  // 注意Y/Z映射
            const dz = star.y - point.z;
            const dist = dx*dx + dy*dy + dz*dz;
            if (dist < bestDist) {
                bestDist = dist;
                best = star;
            }
        }
        return bestDist < 0.001 ? best : null;  // 阈值防止误触
    }

    // ===== 天球网格 =====
    addGrid() {
        // 天球赤道（青色）
        const eqPoints = [];
        for (let i = 0; i <= 128; i++) {
            const angle = (i / 128) * Math.PI * 2;
            eqPoints.push(new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle)));
        }
        const eqGeom = new THREE.BufferGeometry().setFromPoints(eqPoints);
        const eqMat = new THREE.LineBasicMaterial({
            color: 0x00ffff, transparent: true, opacity: 0.4
        });
        this.scene.add(new THREE.Line(eqGeom, eqMat));

        // 赤纬圈（灰色虚线，每30°）
        for (let dec = -60; dec <= 60; dec += 30) {
            if (dec === 0) continue;
            const decRad = (dec * Math.PI) / 180;
            const radius = Math.cos(decRad);
            const height = Math.sin(decRad);
            const points = [];
            for (let i = 0; i <= 64; i++) {
                const angle = (i / 64) * Math.PI * 2;
                points.push(new THREE.Vector3(
                    radius * Math.cos(angle), height, radius * Math.sin(angle)
                ));
            }
            const geom = new THREE.BufferGeometry().setFromPoints(points);
            const mat = new THREE.LineBasicMaterial({
                color: 0x444444, transparent: true, opacity: 0.3
            });
            this.scene.add(new THREE.Line(geom, mat));
        }

        // 赤经线（绿色，每3小时）
        for (let ra = 0; ra < 24; ra += 3) {
            const raRad = (ra * 15 * Math.PI) / 180;
            const points = [];
            for (let i = 0; i <= 50; i++) {
                const decRad = -Math.PI / 2 + (Math.PI * i) / 50;
                points.push(new THREE.Vector3(
                    Math.cos(decRad) * Math.cos(raRad),
                    Math.sin(decRad),
                    Math.cos(decRad) * Math.sin(raRad)
                ));
            }
            const geom = new THREE.BufferGeometry().setFromPoints(points);
            const mat = new THREE.LineBasicMaterial({
                color: 0x00ff00, transparent: true, opacity: 0.2
            });
            this.scene.add(new THREE.Line(geom, mat));
        }
    }

    // ===== 更新星星 =====
    updateStars(stars, brightStars) {
        // 清除旧对象
        if (this.starLayers) {
            this.starLayers.forEach(layer => this.scene.remove(layer));
        }
        this.labels.forEach(l => this.scene.remove(l));
        this.labels = [];
        this.starData = stars;
        this.starLayers = [];

        if (stars.length === 0) return;

        // ===== 按星等分层定义 =====
        // 每层: { maxMag: 该层包含的最暗星等, size: 像素大小, opacity: 透明度 }
        const layers = [
            { maxMag: 1.0,  size: 7,  opacity: 1.0  },   // 极亮星 (≤1等)
            { maxMag: 2.5,  size: 5,  opacity: 0.95 },   // 亮星   (1~2.5等)
            { maxMag: 4.0,  size: 3,  opacity: 0.85 },   // 中等星 (2.5~4等)
            { maxMag: 6.0,  size: 2,  opacity: 0.7  },   // 暗星   (4~6等)
        ];

        // 为每一层创建独立的 Points 对象
        let prevMaxMag = -Infinity;
        for (const layer of layers) {
            // 筛选属于当前层的星星
            const layerStars = stars.filter(
                s => s.mag > prevMaxMag && s.mag <= layer.maxMag
            );
            prevMaxMag = layer.maxMag;

            if (layerStars.length === 0) continue;

            const positions = new Float32Array(layerStars.length * 3);
            const colors = new Float32Array(layerStars.length * 3);

            layerStars.forEach((star, i) => {
                positions[i * 3]     = star.x;
                positions[i * 3 + 1] = star.z;   // Three.js Y轴朝上
                positions[i * 3 + 2] = star.y;

                const color = new THREE.Color(
                    this.SPECTRAL_COLORS[star.spect_class] || 0xaaaaaa
                );
                colors[i * 3]     = color.r;
                colors[i * 3 + 1] = color.g;
                colors[i * 3 + 2] = color.b;
            });

            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

            const material = new THREE.PointsMaterial({
                size: layer.size,
                map: this.circleTexture,        // ← 新增：圆形纹理
                alphaTest: 0.01,                // ← 新增：丢弃完全透明像素，避免方形边框
                vertexColors: true,
                transparent: true,
                opacity: layer.opacity,
                sizeAttenuation: false,
                depthWrite: false
            });

            const points = new THREE.Points(geometry, material);
            points.userData.baseSize = layer.size;
            this.scene.add(points);
            this.starLayers.push(points);
        }

        // ===== 亮星光辉层（可选增强） =====
        const glowStars = stars.filter(s => s.mag <= 2.5);
        if (glowStars.length > 0) {
            const gPos = new Float32Array(glowStars.length * 3);
            const gCol = new Float32Array(glowStars.length * 3);

            glowStars.forEach((star, i) => {
                gPos[i * 3]     = star.x;
                gPos[i * 3 + 1] = star.z;
                gPos[i * 3 + 2] = star.y;

                const c = new THREE.Color(
                    this.SPECTRAL_COLORS[star.spect_class] || 0xaaaaaa
                );
                gCol[i * 3]     = c.r;
                gCol[i * 3 + 1] = c.g;
                gCol[i * 3 + 2] = c.b;
            });

            const gGeom = new THREE.BufferGeometry();
            gGeom.setAttribute('position', new THREE.BufferAttribute(gPos, 3));
            gGeom.setAttribute('color', new THREE.BufferAttribute(gCol, 3));

            const glowMat = new THREE.PointsMaterial({
                size: 12,
                map: this.circleTexture,        // ← 新增
                alphaTest: 0.01,                // ← 新增
                vertexColors: true,
                transparent: true,
                opacity: 0.15,
                sizeAttenuation: false,
                depthWrite: false
            });

            const glowPoints = new THREE.Points(gGeom, glowMat);
            glowPoints.userData.baseSize = 12;
            this.scene.add(glowPoints);
            this.starLayers.push(glowPoints);
        }

        // ===== 亮星文字标注 =====
        if (brightStars && brightStars.length > 0) {
            brightStars.forEach(star => {
                const sprite = this.createTextSprite(star.name);
                sprite.position.set(star.x * 1.05, star.z * 1.05, star.y * 1.05);
                this.scene.add(sprite);
                this.labels.push(sprite);
            });
        }
    }

    createTextSprite(text) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 256;
        canvas.height = 64;

        ctx.font = 'Bold 20px Arial';
        ctx.fillStyle = 'white';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, 128, 32);

        const texture = new THREE.CanvasTexture(canvas);
        const material = new THREE.SpriteMaterial({
            map: texture, transparent: true, depthWrite: false
        });

        const sprite = new THREE.Sprite(material);
        sprite.scale.set(0.12, 0.03, 1);
        return sprite;
    }

    // ===== 渲染循环 =====
    animate() {
        this.animationId = requestAnimationFrame(() => this.animate());
        this.renderer.render(this.scene, this.camera);
    }

    onResize() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    destroy() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.renderer) this.renderer.dispose();
    }
}