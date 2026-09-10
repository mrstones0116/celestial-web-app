// time.js - 观测时间系统（香港时间 UTC+8，精确到秒）
// 支持：自然流动 / 静止 / 手动调整；并计算香港本地恒星时驱动天球周日旋转
class TimeManager {
    constructor() {
        this.mode = 'flow';          // 'flow' 流动 | 'paused' 静止
        this.offsetMs = 0;           // 模拟时间 - 真实时间
        this.frozenMs = Date.now();  // 静止快照
        this.LONGITUDE_E = 114.175;  // 香港东经
        this._listeners = [];
        setInterval(() => this._emit(), 200);
    }
    getSimMs()   { return this.mode === 'flow' ? Date.now() + this.offsetMs : this.frozenMs; }
    getSimDate() { return new Date(this.getSimMs()); }
    setMode(mode) {
        if (mode === this.mode) return;
        if (mode === 'paused') this.frozenMs = this.getSimMs();
        else this.offsetMs = this.frozenMs - Date.now();
        this.mode = mode;
        this._emit();
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
    // 香港时间字符串（精确到秒）
    getHKTString() {
        return new Intl.DateTimeFormat('zh-Hans-HK', {
            timeZone: 'Asia/Hong_Kong', hour12: false,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        }).format(this.getSimDate());
    }
    // 香港本地恒星时（弧度 0~2π）
    getLocalSiderealTime() {
        const ms = this.getSimMs();
        const d = (ms - 946728000000) / 86400000;
        const T = d / 36525;
        let gmst = 280.46061837 + 360.98564736629 * d
                 + 0.000387933 * T * T - (T * T * T) / 38710000;
        let lst = (gmst + this.LONGITUDE_E) % 360;
        if (lst < 0) lst += 360;
        return lst * Math.PI / 180;
    }
    onChange(fn) { this._listeners.push(fn); }
    _emit() { this._listeners.forEach(fn => fn(this)); }
}
window.timeManager = new TimeManager();

// 时间面板 UI 绑定
(function wireTimeUI() {
    function parseHKTLocal(str) {
        const p = str.split('T');
        const ymd = p[0].split('-').map(Number);
        const hms = (p[1] || '00:00:00').split(':').map(Number);
        return Date.UTC(ymd[0], ymd[1] - 1, ymd[2], hms[0] || 0, hms[1] || 0, hms[2] || 0) - 8 * 3600 * 1000;
    }
    const $ = (id) => document.getElementById(id);
    function refresh() {
        const tm = window.timeManager;
        if ($('time-display')) $('time-display').textContent = '🇭 HKT ' + tm.getHKTString();
        if ($('lst-display'))  $('lst-display').textContent  = '本地恒星时 LST: ' + ((tm.getLocalSiderealTime() * 180 / Math.PI) / 15).toFixed(4) + ' h';
        if ($('time-flow-btn'))  $('time-flow-btn').classList.toggle('active', tm.mode === 'flow');
        if ($('time-pause-btn')) $('time-pause-btn').classList.toggle('active', tm.mode === 'paused');
    }
    window.timeManager.onChange(refresh);
    setInterval(refresh, 250);
    refresh();
    if ($('time-flow-btn'))  $('time-flow-btn').onclick  = () => window.timeManager.setMode('flow');
    if ($('time-pause-btn')) $('time-pause-btn').onclick = () => window.timeManager.setMode('paused');
    if ($('time-now-btn'))   $('time-now-btn').onclick   = () => window.timeManager.resetToNow();
    if ($('time-apply-btn')) $('time-apply-btn').onclick = () => {
        const v = $('time-picker').value;
        if (v) window.timeManager.setSimMs(parseHKTLocal(v));
    };
    document.querySelectorAll('[data-time-shift]').forEach(btn => {
        btn.onclick = () => window.timeManager.shiftSimMs(parseFloat(btn.dataset.timeShift));
    });
})();