// time.js - 观测时间系统 + 观测位置 + Epoch 岁差引擎
function _mat3mul(a, b) {
    const r = new Array(9);
    for (let i = 0; i < 3; i++)
        for (let j = 0; j < 3; j++)
            r[i*3+j] = a[i*3]*b[j] + a[i*3+1]*b[3+j] + a[i*3+2]*b[6+j];
    return r;
}

class TimeManager {
    constructor() {
        this.mode = 'flow';
        this.offsetMs = 0;
        this.frozenMs = Date.now();
        this.latitude  = 22.32;      // 观测纬度（默认香港）
        this.longitude = 114.175;    // 观测经度（默认香港）
        this._listeners = [];
        setInterval(() => this._emit(), 200);
    }
    getSimMs()   { return this.mode === 'flow' ? Date.now() + this.offsetMs : this.frozenMs; }
    getSimDate() { return new Date(this.getSimMs()); }
    getEpochYear() { return this.getSimDate().getUTCFullYear(); }
    setLocation(lat, lon) { this.latitude = lat; this.longitude = lon; this._emit(); }
    setMode(mode) {
        if (mode === this.mode) return;
        if (mode === 'paused') this.frozenMs = this.getSimMs();
        else this.offsetMs = this.frozenMs - Date.now();
        this.mode = mode; this._emit();
    }
    setSimMs(ms) {
        if (this.mode === 'flow') this.offsetMs = ms - Date.now();
        else this.frozenMs = ms;
        this._emit();
    }
    shiftSimMs(d) { this.setSimMs(this.getSimMs() + d); }
    resetToNow() {
        this.offsetMs = 0;
        if (this.mode === 'paused') this.frozenMs = Date.now();
        this._emit();
    }
    getHKTString() {
        return new Intl.DateTimeFormat('zh-Hans-HK', {
            timeZone: 'Asia/Hong_Kong', hour12: false,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        }).format(this.getSimDate());
    }
    // 本地恒星时（用观测者经度）
    getLocalSiderealTime() {
        const ms = this.getSimMs();
        const d = (ms - 946728000000) / 86400000;
        const T = d / 36525;
        let gmst = 280.46061837 + 360.98564736629 * d
                 + 0.000387933 * T * T - (T * T * T) / 38710000;
        let lst = (gmst + this.longitude) % 360;
        if (lst < 0) lst += 360;
        return lst * Math.PI / 180;
    }
    // 岁差矩阵（Lieske 1976）：J2000 → 目标历元
    precessionMatrix(year) {
        const T = (year - 2000) / 100;
        const arc = Math.PI / 180 / 3600;
        const zeta  = (2306.2181*T + 0.30188*T*T + 0.017998*T*T*T) * arc;
        const theta = (2004.3109*T - 0.42665*T*T - 0.041833*T*T*T) * arc;
        const z     = (2306.2181*T + 1.09468*T*T + 0.041833*T*T*T) * arc;
        const c1 = Math.cos(-zeta), s1 = Math.sin(-zeta);
        const c2 = Math.cos(theta), s2 = Math.sin(theta);
        const c3 = Math.cos(-z),    s3 = Math.sin(-z);
        const Rz1 = [c1, -s1, 0,  s1, c1, 0,  0, 0, 1];
        const Ry  = [c2, 0, s2,   0, 1, 0,  -s2, 0, c2];
        const Rz2 = [c3, -s3, 0,  s3, c3, 0,  0, 0, 1];
        return _mat3mul(Rz2, _mat3mul(Ry, Rz1));
    }
    onChange(fn) { this._listeners.push(fn); }
    _emit() { this._listeners.forEach(fn => fn(this)); }
}
window.timeManager = new TimeManager();

// ===== UI 绑定 =====
(function wireTimeUI() {
    function parseHKTLocal(str) {
        const p = str.split('T');
        const ymd = p[0].split('-').map(Number);
        const hms = (p[1] || '00:00:00').split(':').map(Number);
        return Date.UTC(ymd[0], ymd[1]-1, ymd[2], hms[0]||0, hms[1]||0, hms[2]||0) - 8*3600*1000;
    }
    const $ = id => document.getElementById(id);
    let lastYear = null;
    function refresh() {
        const tm = window.timeManager;
        if ($('time-display')) $('time-display').textContent = '🇭 HKT ' + tm.getHKTString();
        if ($('lst-display'))  $('lst-display').textContent  = '本地恒星时 LST: ' + ((tm.getLocalSiderealTime()*180/Math.PI)/15).toFixed(4) + ' h';
        if ($('time-flow-btn'))  $('time-flow-btn').classList.toggle('active', tm.mode === 'flow');
        if ($('time-pause-btn')) $('time-pause-btn').classList.toggle('active', tm.mode === 'paused');
        const yr = tm.getEpochYear();
        if ($('epoch-display')) $('epoch-display').textContent = '渲染历元: ' + (yr < 0 ? ('公元前 ' + (-yr)) : ('公元 ' + yr)) + ' 年';
        if (lastYear !== null && yr !== lastYear && window.refreshEpochAll) window.refreshEpochAll();
        lastYear = yr;
    }
    window.timeManager.onChange(refresh);
    setInterval(refresh, 250);
    refresh();
    if ($('time-flow-btn'))  $('time-flow-btn').onclick  = () => window.timeManager.setMode('flow');
    if ($('time-pause-btn')) $('time-pause-btn').onclick = () => window.timeManager.setMode('paused');
    if ($('time-now-btn'))   $('time-now-btn').onclick   = () => window.timeManager.resetToNow();
    if ($('time-apply-btn')) $('time-apply-btn').onclick = () => { const v = $('time-picker').value; if (v) window.timeManager.setSimMs(parseHKTLocal(v)); };
    document.querySelectorAll('[data-time-shift]').forEach(btn => {
        btn.onclick = () => window.timeManager.shiftSimMs(parseFloat(btn.dataset.timeShift));
    });
    // 观测位置面板
    const latIn = $('loc-lat'), lonIn = $('loc-lon'), preset = $('loc-preset');
    function applyLoc(lat, lon, label) {
        if (isNaN(lat) || isNaN(lon)) return;
        lat = Math.max(-90, Math.min(90, lat));
        lon = Math.max(-180, Math.min(180, lon));
        window.timeManager.setLocation(lat, lon);
        if (latIn) latIn.value = lat.toFixed(2);
        if (lonIn) lonIn.value = lon.toFixed(2);
        if ($('loc-info')) $('loc-info').textContent = (label||'自定义') + ' (' + Math.abs(lat).toFixed(2) + '°' + (lat>=0?'N':'S') + ', ' + Math.abs(lon).toFixed(2) + '°' + (lon>=0?'E':'W') + ')';
    }
    if ($('loc-apply')) $('loc-apply').onclick = () => applyLoc(parseFloat(latIn.value), parseFloat(lonIn.value), '自定义');
    if (preset) preset.onchange = () => { const v = preset.value.split(',').map(Number); applyLoc(v[0], v[1], preset.options[preset.selectedIndex].text); };
    if ($('loc-gps')) $('loc-gps').onclick = () => {
        if (!navigator.geolocation) { if ($('loc-info')) $('loc-info').textContent = '❌ 此环境不支持 GPS'; return; }
        navigator.geolocation.getCurrentPosition(
            pos => applyLoc(pos.coords.latitude, pos.coords.longitude, 'GPS 定位'),
            ()  => { if ($('loc-info')) $('loc-info').textContent = '❌ GPS 失败，请手动输入'; }
        );
    };
})();