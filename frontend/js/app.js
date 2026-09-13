/**
 * app.js - 主应用逻辑
 * API 使用相对路径，自动适配启动器动态端口
 */
const API_BASE = ''; // 相对路径，杜绝端口错配
let scene3d = null;
let chart2d = null;

document.addEventListener('DOMContentLoaded', () => {
    chart2d = new Chart2D('chart-2d');
    setupEventListeners();
    setupUI();
    loadSpectralInfo();
});

function setupEventListeners() {
    const btnLoad = document.getElementById('btn-load');
    if (btnLoad) btnLoad.addEventListener('click', loadData);
    
    const btnApply = document.getElementById('btn-apply');
    if (btnApply) btnApply.addEventListener('click', applyFilter);
    
    const btnReset = document.getElementById('btn-reset');
    if (btnReset) btnReset.addEventListener('click', resetFilter);
    
    const slider = document.getElementById('mag-slider');
    if (slider) {
        slider.addEventListener('input', () => {
            const valEl = document.getElementById('mag-value');
            if (valEl) valEl.textContent = parseFloat(slider.value).toFixed(2);
        });
    }
}

/* ===== 抽屉菜单 + 全屏 + 退出程序 + 显示控制 ===== */
function setupUI() {
    const left  = document.getElementById('left-drawer');
    const right = document.getElementById('right-drawer');
    const bL = document.getElementById('toggle-left');
    const bR = document.getElementById('toggle-right');
    const bF = document.getElementById('toggle-fullscreen');
    const bQ = document.getElementById('quit-app');

    const sync = () => {
        if (bL && left)  bL.textContent = left.classList.contains('open')  ? '◀' : '☰';
        if (bR && right) bR.textContent = right.classList.contains('open') ? '▶' : '📊';
    };
    if (bL && left)  bL.addEventListener('click', () => { left.classList.toggle('open');  sync(); });
    if (bR && right) bR.addEventListener('click', () => { right.classList.toggle('open'); sync(); });

    // ⛶ 全屏切换
    if (bF) {
        bF.addEventListener('click', () => {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.toggle_fullscreen) {
                window.pywebview.api.toggle_fullscreen();
            } else if (!document.fullscreenElement) {
                const p = document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
                if (p && p.catch) p.catch(() => {});
            } else if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        });
    }

    // 红色 ✕ 强制结束程序
    if (bQ) {
        bQ.addEventListener('click', () => {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.quit) {
                window.pywebview.api.quit();
            } else {
                window.close();
            }
        });
    }

    // ===== 显示控制开关 =====
    const gT = document.getElementById('toggle-ground');
    const lT = document.getElementById('toggle-labels');
    const nT = document.getElementById('toggle-lines');
    const cT = document.getElementById('toggle-const-names');
    const grT = document.getElementById('toggle-grid');
    const dsoT = document.getElementById('toggle-dso');
    if (dsoT) dsoT.onchange = () => { if (scene3d) scene3d.setDSOVisible(dsoT.checked); };
    if (grT) grT.onchange = () => { if (window.celestialScene) window.celestialScene.setGridVisible(grT.checked); };
    if (gT) gT.onchange = () => { if (scene3d) scene3d.setGroundVisible(gT.checked); };
    if (lT) lT.onchange = () => { if (scene3d) scene3d.setLabelsVisible(lT.checked); };
    if (nT) nT.onchange = () => { if (scene3d) scene3d.setLinesVisible(nT.checked); };
    if (cT) cT.onchange = () => { if (scene3d) scene3d.setConstNamesVisible(cT.checked); };

    // ===== 地理位置面板 =====
    const latIn = document.getElementById('loc-lat');
    const lonIn = document.getElementById('loc-lon');
    const locPreset = document.getElementById('loc-preset');
    function applyLoc(lat, lon, label) {
        if (isNaN(lat) || isNaN(lon)) return;
        lat = Math.max(-90, Math.min(90, lat));
        lon = Math.max(-180, Math.min(180, lon));
        if (window.timeManager) window.timeManager.setLocation(lat, lon);
        if (latIn) latIn.value = lat.toFixed(2);
        if (lonIn) lonIn.value = lon.toFixed(2);
        const locInfo = document.getElementById('loc-info');
        if (locInfo) locInfo.textContent = (label || '自定义') + ' (' +
            Math.abs(lat).toFixed(2) + '°' + (lat >= 0 ? 'N' : 'S') + ', ' +
            Math.abs(lon).toFixed(2) + '°' + (lon >= 0 ? 'E' : 'W') + ')';
    }
    const locApply = document.getElementById('loc-apply');
    if (locApply) locApply.onclick = () => applyLoc(parseFloat(latIn.value), parseFloat(lonIn.value), '自定义');
    if (locPreset) locPreset.onchange = () => {
        const v = locPreset.value.split(',').map(Number);
        applyLoc(v[0], v[1], locPreset.options[locPreset.selectedIndex].text);
    };
    const locGps = document.getElementById('loc-gps');
    if (locGps) locGps.onclick = () => {
        if (!navigator.geolocation) {
            const locInfo = document.getElementById('loc-info');
            if (locInfo) locInfo.textContent = '❌ 此环境不支持 GPS';
            return;
        }
        navigator.geolocation.getCurrentPosition(
            pos => applyLoc(pos.coords.latitude, pos.coords.longitude, 'GPS 定位'),
            () => {
                const locInfo = document.getElementById('loc-info');
                if (locInfo) locInfo.textContent = '❌ GPS 失败，请手动输入';
            }
        );
    };
    sync();
}

/* ===== 加载数据 ===== */
async function loadData() {
    showLoading(true);
    const statusEl = document.getElementById('load-status');
    if (statusEl) statusEl.textContent = '正在加载 HYG 星表数据...';
    try {
        const res  = await fetch(`${API_BASE}/api/load`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            if (statusEl) {
                statusEl.textContent = `✅ ${data.message}`;
                statusEl.style.color = '#27ae60';
            }
            const fp = document.getElementById('filter-panel');
            const sp = document.getElementById('stats-panel');
            const ph = document.getElementById('placeholder-3d');
            if (fp) fp.style.display = 'block';
            if (sp) sp.style.display  = 'block';
            if (ph) ph.style.display = 'none';

            if (!scene3d) {
                scene3d = new CelestialScene3D('canvas-container');
                window.celestialScene = scene3d;
                scene3d.init();
            }
            await refreshData(6.0);
            // 加载 88 星座标准连线（本地优先/在线回退/非阻塞）
            if (scene3d.loadConstellationLines) scene3d.loadConstellationLines();
            // ★ 修复初次加载星座信息不显示：等首帧矩阵稳定后强制重刷一次
            setTimeout(() => {
                if (scene3d && scene3d.refreshConstellationInfo) scene3d.refreshConstellationInfo();
            }, 150);
        } else {
            if (statusEl) {
                statusEl.textContent = `❌ ${data.message}`;
                statusEl.style.color = '#e74c3c';
            }
        }
    } catch (err) {
        if (statusEl) {
            statusEl.textContent = `❌ 请求失败: ${err.message}`;
            statusEl.style.color = '#e74c3c';
        }
    } finally {
        showLoading(false);
    }
}

/* ===== 刷新数据 ===== */
/* ===== 刷新数据 ===== */
async function refreshData(maxMag) {
    try {
        const [starsRes, brightRes, statsRes, constRes, topRes] = await Promise.all([
            fetch(`${API_BASE}/api/stars?max_mag=${maxMag}`),
            fetch(`${API_BASE}/api/bright-stars?max_mag=2.5`),
            fetch(`${API_BASE}/api/stats?max_mag=${maxMag}`),
            fetch(`${API_BASE}/api/constellations?max_mag=${maxMag}`),
            fetch(`${API_BASE}/api/top-bright?limit=15&max_mag=${maxMag}`)
        ]);
        const starsData  = await starsRes.json();
        const brightData = await brightRes.json();
        const statsData  = await statsRes.json();
        const constData  = await constRes.json();
        const topData    = await topRes.json();

        // ★ 先更新数据面板（不受 3D 渲染异常影响）
        updateStats(statsData);
        updateConstellationTable(constData.constellations);
        updateBrightStarsTable(topData.stars);
        const filterInfo = document.getElementById('filter-info');
        if (filterInfo) filterInfo.textContent = `当前显示: ${statsData.current_count} / ${statsData.total_stars} 颗星`;

        // ★ 再更新 3D 渲染（独立 try-catch，避免拖累数据面板）
        try {
            if (scene3d) scene3d.updateStars(starsData.stars, brightData.stars);
        } catch (renderErr) {
            console.error('3D 渲染失败:', renderErr);
        }
        try {
            if (chart2d) chart2d.draw(starsData.stars);
        } catch (chartErr) {
            console.error('2D 图表渲染失败:', chartErr);
        }
    } catch (err) {
        console.error('刷新数据失败:', err);
    }
}

function applyFilter() {
    const slider = document.getElementById('mag-slider');
    if (slider) refreshData(parseFloat(slider.value));
}
function resetFilter() {
    const slider = document.getElementById('mag-slider');
    const magValue = document.getElementById('mag-value');
    if (slider) slider.value = 6;
    if (magValue) magValue.textContent = '6.00';
    refreshData(6.0);
}

function updateStats(s) {
    const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setTxt('stat-total', s.total_stars);
    setTxt('stat-current', s.current_count);
    setTxt('stat-avg-mag', s.avg_mag);
    setTxt('stat-min-mag', s.min_mag);
    setTxt('stat-avg-dist', `${s.avg_dist_ly} ly`);
    setTxt('stat-const-count', s.constellation_count);
}

function updateConstellationTable(list) {
    const tbody = document.querySelector('#constellation-table tbody');
    if (!tbody) return;
    tbody.innerHTML = (list || []).slice(0, 30).map(c =>
        `<tr><td>${c.constellation}</td><td>${c.star_count}</td><td>${c.brightest_mag}</td><td>${c.dimmest_mag}</td><td>${c.avg_mag}</td></tr>`
    ).join('');
}

function updateBrightStarsTable(stars) {
    const tbody = document.querySelector('#bright-stars-table tbody');
    if (!tbody) return;
    tbody.innerHTML = (stars || []).map(s =>
        `<tr><td>${s.name}</td><td>${s.constellation}</td><td>${s.ra_hours}</td><td>${s.dec}</td><td>${s.mag}</td><td>${s.absmag ?? '-'}</td><td>${s.spect}</td><td>${s.dist_ly}</td></tr>`
    ).join('');
}

async function loadSpectralInfo() {
    try {
        const res  = await fetch(`${API_BASE}/api/spectral-info`);
        const data = await res.json();
        const legend = document.getElementById('spectral-legend');
        if (!legend) return;
        legend.innerHTML = Object.entries(data.info).map(([key, info]) => `
            <div class="spectral-item">
                <span class="spectral-dot" style="background:${info.color}"></span>
                <span>${info.name} - ${info.color_name} ${info.temp}</span>
            </div>`).join('');
    } catch (err) {
        console.log('光谱信息API未就绪');
    }
}

// ===== Epoch 时间旅行：年份变化时本地重建 3D 星空 + 重画 2D 图 =====
window.refreshEpochAll = function () {
    if (scene3d && scene3d.refreshEpoch) scene3d.refreshEpoch();
    if (chart2d && scene3d && scene3d.starData) chart2d.draw(scene3d.starData);
};

function showLoading(show) {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.style.display = show ? 'flex' : 'none';
}