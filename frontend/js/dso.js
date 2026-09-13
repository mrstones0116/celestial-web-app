/**
 * dso.js - 深空天体加载（Messier 全 110 + NGC/IC 至 14 等）
 * 本地 data/ 优先 → 在线 d3-celestial 回退；GeoJSON 解析后注入 scene3d
 */
(function () {
    const SOURCES = [
        { local: 'data/messier.json', remote: 'https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/messier.json' },
        { local: 'data/dsos.14.json', remote: 'https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/dsos.14.json' }
    ];
    // 类型 → 中文标签 + 颜色族
    window.DSO_TYPES = {
        gg: { label: '星系团', family: 'gal' },   g:  { label: '星系', family: 'gal' },
        s:  { label: '旋涡星系', family: 'gal' },  s0: { label: '透镜状星系', family: 'gal' },
        sd: { label: '矮星系', family: 'gal' },    i:  { label: '不规则星系', family: 'gal' },
        e:  { label: '椭圆星系', family: 'gal' },  oc: { label: '疏散星团', family: 'ocl' },
        gc: { label: '球状星团', family: 'glob' }, dn: { label: '暗星云', family: 'neb' },
        bn: { label: '亮星云', family: 'neb' },    sfr:{ label: '恒星形成区', family: 'neb' },
        rn: { label: '反射星云', family: 'neb' },  en: { label: '发射星云', family: 'neb' },
        pn: { label: '行星状星云', family: 'neb' },snr:{ label: '超新星遗迹', family: 'neb' }
    };
    window.DSO_FAMILY_COLORS = { gal: 0xffb066, ocl: 0x66ffd0, glob: 0xffe066, neb: 0xff66cc, def: 0xaaaaff };

    function fetchTO(url, ms) {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), ms);
        return fetch(url, { signal: ctrl.signal }).finally(() => clearTimeout(t));
    }
    function parse(gj, out, seen) {
        for (const f of (gj.features || [])) {
            const p = f.properties || {};
            const coords = f.geometry && f.geometry.coordinates;
            if (!coords || coords.length < 2) continue;
            const id = (f.id || p.desig || '').trim();
            if (!id || seen.has(id)) continue;
            seen.add(id);
            const ra = coords[0] * Math.PI / 180, dec = coords[1] * Math.PI / 180;
            const mag = parseFloat(p.mag);
            const name = id.replace(/\s+/g, '');
            const isMessier = /^M\d+$/.test(name);   // ★ 免费版标记
            out.push({
                name, type: p.type || '',
                mag: isNaN(mag) ? 99 : mag,
                dim: p.dim || '',
                isMessier,                            // ★ 存进数据
                x: Math.cos(dec) * Math.cos(ra),
                y: Math.cos(dec) * Math.sin(ra),
                z: Math.sin(dec)
            });
        }
    }
    function loadOne(src) {
        return fetchTO(src.local, 3000)
            .then(r => { if (!r.ok) throw 0; return r.json(); })
            .catch(() => fetchTO(src.remote, 20000).then(r => { if (!r.ok) throw 0; return r.json(); }));
    }
    function tryLoad() {
        const scene = window.celestialScene;
        if (!scene || !scene.addDSOs) { setTimeout(tryLoad, 1000); return; }  // 等星表加载后注入
        const out = [], seen = new Set();
        Promise.all(SOURCES.map(s => loadOne(s).catch(() => null)))
            .then(gjs => {
                gjs.forEach(gj => { if (gj) parse(gj, out, seen); });
                if (out.length) scene.addDSOs(out);
            });
    }
    if (document.readyState === 'complete') tryLoad();
    else window.addEventListener('load', tryLoad);
})();