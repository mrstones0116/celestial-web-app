// time.js - 观测时间系统（仿 Stellarium）+ 岁差 + 章动
// 兼容当前 scene3d.js (flowRate, latitude, longitude, precessionMatrix)
// 兼容当前 app.js (setLocation)
// 兼容当前 index.html (年月日时分秒编辑器, 流速按钮, 历元显示)

function _mat3mul(a, b) {
    const r = new Array(9);
    for (let i = 0; i < 3; i++)
        for (let j = 0; j < 3; j++)
            r[i*3+j] = a[i*3]*b[j] + a[i*3+1]*b[3+j] + a[i*3+2]*b[6+j];
    return r;
}

class TimeManager {
    constructor() {
        this.simMs = Date.now();
        this.flowRate = 1;           // 0=静止, 0.5/1/2/5/10
        this.lastRealMs = Date.now();
        this.latitude = 22.32;       // 默认香港
        this.longitude = 114.175;
        this._listeners = [];
        setInterval(() => this._tick(), 50);
    }
    
    _tick() {
        const now = Date.now();
        const elapsed = now - this.lastRealMs;
        this.lastRealMs = now;
        if (this.flowRate > 0) this.simMs += elapsed * this.flowRate;
        this._emit();
    }
    
    getSimMs() { return this.simMs; }
    getSimDate() { return new Date(this.simMs); }
    getEpochYear() { return this.getSimDate().getUTCFullYear(); }
    
    setFlowRate(rate) { this.flowRate = rate; this._emit(); }
    setSimMs(ms) { this.simMs = ms; this._emit(); }
    setLocation(lat, lon) { 
        this.latitude = lat; 
        this.longitude = lon; 
        this._emit(); 
    }

    // HKT (UTC+8) 时间分量
    getHKTComponents() {
        const d = new Date(this.simMs + 8 * 3600 * 1000);
        return {
            year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate(),
            hour: d.getUTCHours(), minute: d.getUTCMinutes(), second: d.getUTCSeconds()
        };
    }
    setHKTComponents(c) {
        const hktMs = Date.UTC(c.year, c.month - 1, c.day, c.hour, c.minute, c.second);
        this.simMs = hktMs - 8 * 3600 * 1000;
        this._emit();
    }
    adjustComponent(comp, delta) {
        const c = this.getHKTComponents();
        c[comp] += delta;
        this.setHKTComponents(c);
    }
    setComponent(comp, value) {
        const c = this.getHKTComponents();
        c[comp] = value;
        this.setHKTComponents(c);
    }

    getHKTString() {
        return new Intl.DateTimeFormat('zh-Hans-HK', {
            timeZone: 'Asia/Hong_Kong', hour12: false,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        }).format(this.getSimDate());
    }
    
    getLocalSiderealTime() {
        const d = (this.simMs - 946728000000) / 86400000;
        const T = d / 36525;
        let gmst = 280.46061837 + 360.98564736629 * d
                 + 0.000387933 * T * T - (T * T * T) / 38710000;
        let lst = (gmst + this.longitude) % 360;
        if (lst < 0) lst += 360;
        return lst * Math.PI / 180;
    }
    
    // ===== 岁差 + 章动组合矩阵：J2000 平位置 → 目标历元真位置 =====
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
        const prec = _mat3mul(Rz2, _mat3mul(Ry, Rz1));
        const nut = this.nutationMatrix(year);
        return _mat3mul(nut, prec);
    }
    
    nutationAngles(T) {
        const D2R = Math.PI / 180;
        const omega = (125.04452 - 1934.136261 * T) * D2R;
        const L  = (280.4665 + 36000.7698 * T) * D2R;
        const Lp = (218.3165 + 481267.8813 * T) * D2R;
        const dPsi = (-17.20 * Math.sin(omega) - 1.32 * Math.sin(2*L)
                      - 0.23 * Math.sin(2*Lp) + 0.21 * Math.sin(2*omega)) / 206265;
        const dEps = ( 9.20 * Math.cos(omega) + 0.57 * Math.cos(2*L)
                      + 0.10 * Math.cos(2*Lp) - 0.09 * Math.cos(2*omega)) / 206265;
        return { dPsi, dEps };
    }
    
    nutationMatrix(year) {
        const T = (year - 2000) / 100;
        const { dPsi, dEps } = this.nutationAngles(T);
        const eps0 = (23.4392911 - 0.0130042 * T) * Math.PI / 180;
        const eps = eps0 + dEps;
        const cPsi = Math.cos(dPsi), sPsi = Math.sin(dPsi);
        const cE0 = Math.cos(eps0), sE0 = Math.sin(eps0);
        const cE = Math.cos(eps),  sE = Math.sin(eps);
        const Rx1 = [1, 0, 0,  0, cE0, -sE0,  0, sE0, cE0];
        const Rz  = [cPsi, sPsi, 0,  -sPsi, cPsi, 0,  0, 0, 1];
        const Rx2 = [1, 0, 0,  0, cE, sE,  0, -sE, cE];
        return _mat3mul(Rx2, _mat3mul(Rz, Rx1));
    }

    onChange(fn) { this._listeners.push(fn); }
    _emit() { this._listeners.forEach(fn => fn(this)); }
}

window.timeManager = new TimeManager();

// ===== 时间面板 UI 绑定（兼容当前 index.html 的年月日编辑器与流速按钮）=====
(function wireTimeUI() {
    const $ = id => document.getElementById(id);
    const tm = window.timeManager;
    let lastYear = null;   // ★ 检测年份变化，触发岁差重算
    
    function refresh() {
        const c = tm.getHKTComponents();
        const setVal = (id, val) => {
            const el = $(id);
            if (el && document.activeElement !== el) el.value = String(val).padStart(2, '0');
        };
        setVal('time-year', c.year);
        setVal('time-month', c.month);
        setVal('time-day', c.day);
        setVal('time-hour', c.hour);
        setVal('time-minute', c.minute);
        setVal('time-second', c.second);
        
        if ($('lst-display')) {
            const lstH = (tm.getLocalSiderealTime() * 180 / Math.PI) / 15;
            $('lst-display').textContent = 'LST: ' + lstH.toFixed(4) + ' h';
        }
        
        const yr = tm.getEpochYear();
        if ($('epoch-display')) {
            $('epoch-display').textContent = '历元: ' + (yr < 0 ? ('公元前 ' + (-yr)) : ('公元 ' + yr));
        }
        
        // ★★★ 核心：年份变化 → 重算岁差（重绘星空 + 星座名 + 连线）★★★
        if (lastYear !== null && yr !== lastYear) {
            if (window.refreshEpochAll) window.refreshEpochAll();
        }
        lastYear = yr;
        
        document.querySelectorAll('.flow-rate-btn').forEach(btn => {
            btn.classList.toggle('active', parseFloat(btn.dataset.rate) === tm.flowRate);
        });
    }
    
    tm.onChange(refresh);
    setInterval(refresh, 250);
    refresh();

    // 时间分量上下按钮
    document.querySelectorAll('.time-step-btn').forEach(btn => {
        btn.onclick = () => tm.adjustComponent(btn.dataset.comp, parseInt(btn.dataset.dir, 10));
    });
    
    // 时间输入框
    ['year', 'month', 'day', 'hour', 'minute', 'second'].forEach(comp => {
        const input = $(`time-${comp}`);
        if (input) {
            input.addEventListener('change', () => {
                let val = parseInt(input.value, 10);
                if (isNaN(val)) return;
                tm.setComponent(comp, val);
            });
        }
    });
    
    // 流速按钮
    document.querySelectorAll('.flow-rate-btn').forEach(btn => {
        btn.onclick = () => tm.setFlowRate(parseFloat(btn.dataset.rate));
    });
    
    // 回到现在
    if ($('time-now-btn')) {
        $('time-now-btn').onclick = () => {
            tm.setSimMs(Date.now());
            tm.setFlowRate(1);
        };
    }
})();