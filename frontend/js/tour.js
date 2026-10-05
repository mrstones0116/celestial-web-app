/**
 * tour.js - 智能星空导览
 * 核心：不依赖用户输入。基于「此时此刻此地」实时可见星空自动构建 Prompt，
 *       交给 AI 后端生成导览路线；后端不可用时用本地算法生成兜底导览。
 */
const Tour = {
    sessionId: null,
    currentPlan: null,
    currentStepIndex: 0,
    apiBase: "/api/tour",
    _busy: false,
    _lastState: null,

    // ============================================================
    //  一、基础工具
    // ============================================================

    _setStatus(text, isError = false) {
        const el = document.getElementById("tour-status");
        if (!el) return;
        el.textContent = text || "";
        el.style.color = isError ? "#ff8a8a" : "";
    },

    async _post(path, body) {
        const opts = {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        };
        if (body !== undefined) opts.body = JSON.stringify(body);
        let res;
        try {
            res = await fetch(this.apiBase + path, opts);
        } catch (e) {
            console.warn("[Tour] 网络错误", e);
            return null;
        }
        if (!res.ok) {
            console.warn("[Tour] HTTP", res.status);
            return null;
        }
        try {
            return await res.json();
        } catch (e) {
            console.warn("[Tour] JSON 解析失败", e);
            return null;
        }
    },

    async _ensureSession() {
        if (this.sessionId) return true;
        const data = await this._post("/sessions", {});
        if (!data || !data.session_id) return false;
        this.sessionId = data.session_id;
        return true;
    },

    // ============================================================
    //  二、实时星空可见性分析
    // ============================================================

    /** 赤道场景坐标 (x, y, z) → 地平高度角/方位角（度） */
    _altAz(x, y, z) {
        const scene = window.celestialScene;
        const v = new THREE.Vector3(x, z, -y);   // 与 starLayers 的映射一致
        if (scene && scene.horizonGroup) v.applyMatrix4(scene.horizonGroup.matrix);
        const alt = Math.asin(Math.max(-1, Math.min(1, v.y))) * 180 / Math.PI;
        let az = Math.atan2(v.x, -v.z) * 180 / Math.PI;
        if (az < 0) az += 360;
        return { alt, az };
    },

    /** 太阳系天体：场景位置 (x, z, -y) → { ra, dec, alt, az } */
    _bodyInfo(p) {
        const ex = p.x, ey = -p.z, ez = p.y;     // 还原赤道向量
        const { alt, az } = this._altAz(ex, ey, ez);
        let ra = Math.atan2(ey, ex) * 180 / Math.PI;
        if (ra < 0) ra += 360;
        const dec = Math.asin(Math.max(-1, Math.min(1, ez))) * 180 / Math.PI;
        return { ra, dec, alt, az };
    },

    /**
     * 扫描当前星图，产出「此刻地平线上方」的完整快照
     * @returns {null|Object} 星图未就绪时返回 null
     */
    skyState() {
        const scene = window.celestialScene;
        const tm = window.timeManager;
        if (!scene || !tm || !scene.horizonGroup) return null;
        if (!scene.starData || !scene.starData.length) return null;

        const MIN_ALT = 8;   // 低于 8° 受大气消光与地景影响严重，不推荐
        const pad = n => String(n).padStart(2, "0");
        const c = tm.getHKTComponents();

        const st = {
            timeStr: `${c.year}-${pad(c.month)}-${pad(c.day)} ${pad(c.hour)}:${pad(c.minute)}`,
            locStr: `${Math.abs(tm.latitude).toFixed(2)}°${tm.latitude >= 0 ? "N" : "S"}, ` +
                    `${Math.abs(tm.longitude).toFixed(2)}°${tm.longitude >= 0 ? "E" : "W"}`,
            sunAlt: null, planets: [], constellations: [], brightStars: [], dsos: []
        };

        // ---------- 太阳高度（判断白天/黑夜）----------
        if (scene.sunGroup) st.sunAlt = this._bodyInfo(scene.sunGroup.position).alt;

        // ---------- 恒星逐颗换算地平坐标 ----------
        const visible = [];
        for (const s of scene.starData) {
            const { alt, az } = this._altAz(s.x, s.y, s.z);
            if (alt < MIN_ALT) continue;
            visible.push({ s, alt, az });
        }

        // ---------- 星座聚合 ----------
        const agg = new Map();
        for (const v of visible) {
            const key = v.s.constellation;
            if (!key) continue;
            let g = agg.get(key);
            if (!g) {
                g = { key, stars: [], sumX: 0, sumY: 0, sumZ: 0, maxAlt: -90 };
                agg.set(key, g);
            }
            g.stars.push(v);
            g.sumX += v.s.x; g.sumY += v.s.y; g.sumZ += v.s.z;
            if (v.alt > g.maxAlt) g.maxAlt = v.alt;
        }

        const cons = [];
        for (const g of agg.values()) {
            const sorted = g.stars.slice().sort((a, b) => a.s.mag - b.s.mag);
            const brightest = sorted[0].s;
            const notable = sorted.filter(v => v.s.mag <= 3.5).length;
            const len = Math.hypot(g.sumX, g.sumY, g.sumZ) || 1;
            const cx = g.sumX / len, cy = g.sumY / len, cz = g.sumZ / len;
            const centerRa = (Math.atan2(cy, cx) * 180 / Math.PI + 360) % 360;
            const centerDec = Math.asin(Math.max(-1, Math.min(1, cz))) * 180 / Math.PI;
            const score = notable * 1.2 +
                          (4.2 - Math.min(4.2, brightest.mag)) * 1.6 +
                          g.maxAlt / 40;
            cons.push({
                key: g.key,
                zh: CON_ZH[g.key] || g.key,
                count: g.stars.length,
                notable,
                maxAlt: g.maxAlt,
                brightest: { name: brightest.name, mag: brightest.mag },
                stars: sorted.slice(0, 5).map(v => ({
                    name: v.s.name, mag: v.s.mag, alt: v.alt,
                    ra_hours: v.s.ra_hours, dec: v.s.dec
                })),
                centerRa, centerDec, score
            });
        }
        cons.sort((a, b) => b.score - a.score);
        st.constellations = cons.slice(0, 6);

        // ---------- 亮星 TOP ----------
        st.brightStars = visible
            .filter(v => v.s.name && v.s.mag <= 2.6)
            .sort((a, b) => a.s.mag - b.s.mag)
            .slice(0, 10)
            .map(v => ({
                name: v.s.name, mag: v.s.mag, alt: v.alt,
                constellation: CON_ZH[v.s.constellation] || v.s.constellation || "",
                ra_hours: v.s.ra_hours, dec: v.s.dec
            }));

        // ---------- 行星 / 月球 ----------
        const bodyKeys = ["Moon", "Venus", "Jupiter", "Saturn",
                          "Mars", "Mercury", "Uranus", "Neptune"];
        for (const k of bodyKeys) {
            let p = null;
            if (k === "Moon") p = scene.moonGroup && scene.moonGroup.position;
            else if (scene.solarBodies && scene.solarBodies[k]) p = scene.solarBodies[k].dot.position;
            if (!p) continue;
            const info = this._bodyInfo(p);
            if (info.alt < MIN_ALT) continue;
            const pi = (scene._planetInfo && scene._planetInfo[k]) || {};
            st.planets.push({
                key: k, zh: SOLAR_ZH[k] || k,
                ra: info.ra, dec: info.dec, alt: info.alt, az: info.az,
                mag: pi.mag != null ? pi.mag : null
            });
        }
        st.planets.sort((a, b) =>
            (a.mag == null ? 99 : a.mag) - (b.mag == null ? 99 : b.mag));

        // ---------- 深空天体（Messier）----------
        for (const d of (scene.dsoData || [])) {
            if (!d.isMessier || d.mag > 9) continue;
            const { alt, az } = this._altAz(d.x, d.y, d.z);
            if (alt < MIN_ALT) continue;
            st.dsos.push({
                name: d.name, mag: d.mag, dim: d.dim, alt, az,
                ra: (Math.atan2(d.y, d.x) * 180 / Math.PI + 360) % 360,
                dec: Math.asin(Math.max(-1, Math.min(1, d.z))) * 180 / Math.PI
            });
        }
        st.dsos.sort((a, b) => a.mag - b.mag);
        st.dsos = st.dsos.slice(0, 8);

        return st;
    },

    // ============================================================
    //  三、Prompt 构建（用户无需输入任何内容）
    // ============================================================

    buildPrompt(st) {
        const L = [];
        L.push("请根据下面这份「实时星空观测报告」，生成一份今晚的星空导览，" +
               "推荐值得观测的星座和天体。");
        L.push("");
        L.push(`【观测时间】${st.timeStr}（香港时间 UTC+8）`);
        L.push(`【观测地点】${st.locStr}`);
        if (st.sunAlt != null) {
            const cond = st.sunAlt > 0 ? "（当前为白天）"
                       : st.sunAlt > -6 ? "（曙暮光中）"
                       : "（天文黑夜，观星条件良好）";
            L.push(`【太阳高度角】${st.sunAlt.toFixed(1)}°${cond}`);
        }
        L.push("");
        L.push("【此刻地平线以上（高度角 > 8°）可见天体】");

        if (st.planets.length) {
            L.push("· 行星/太阳系：" + st.planets.map(p =>
                `${p.zh}${p.mag != null ? `（${p.mag} 等）` : ""}` +
                `，高度 ${p.alt.toFixed(0)}°，方位 ${p.az.toFixed(0)}°`
            ).join("；"));
        }
        if (st.constellations.length) {
            L.push("· 星座：" + st.constellations.map(c =>
                `${c.zh}（${c.notable} 颗亮于 3.5 等的星可见，` +
                `最亮 ${c.brightest.name} ${c.brightest.mag} 等，` +
                `最高高度 ${c.maxAlt.toFixed(0)}°）`
            ).join("；"));
        }
        if (st.brightStars.length) {
            L.push("· 亮星：" + st.brightStars.slice(0, 8).map(b =>
                `${b.name}（${b.constellation}，${b.mag} 等，高度 ${b.alt.toFixed(0)}°）`
            ).join("；"));
        }
        if (st.dsos.length) {
            L.push("· 深空天体：" + st.dsos.slice(0, 5).map(d =>
                `${d.name}（${d.mag} 等，高度 ${d.alt.toFixed(0)}°）`
            ).join("；"));
        }
        if (!st.planets.length && !st.constellations.length && !st.dsos.length) {
            L.push("（此刻几乎没有明显可见天体，请给出一般性的星空观测建议）");
        }

        L.push("");
        L.push("要求：");
        L.push("1. 按观赏价值排序，优先级：行星/月球 → 著名星座 → 深空天体；");
        L.push("2. 共 5~8 步，每步给出目标名称、看点解说" +
               "（含最佳观测时段、文化典故、观测小贴士、冷知识）；");
        L.push("3. 每步附带 camera 参数：center_ra_deg、center_dec_deg、fov_deg；");
        L.push("4. 全部使用简体中文。");
        return L.join("\n");
    },

    // ============================================================
    //  四、自动导览入口
    // ============================================================

    async autoStart() {
        if (this._busy) return;
        this._busy = true;
        try {
            const st = this.skyState();
            if (!st) {
                this._setStatus("⏳ 星图尚未就绪，请先加载 HYG 星表数据", true);
                const ctx = document.getElementById("tour-context");
                if (ctx) ctx.textContent = "⏳ 等待星表数据…";
                return;
            }
            this._lastState = st;

            // 更新上下文行（用户不用输入任何东西）
            const ctx = document.getElementById("tour-context");
            if (ctx) {
                ctx.textContent =
                    `🕐 ${st.timeStr} · 📍 ${st.locStr}\n` +
                    `可见：星座 ${st.constellations.length} 个 / 行星 ${st.planets.length} 个 / ` +
                    `深空 ${st.dsos.length} 个`;
            }

            const prompt = this.buildPrompt(st);
            this._setStatus("🤖 正在结合实时星空生成导览…");
            this._showPanel(false);

            // ---- 优先走 AI 后端 ----
            if (await this._ensureSession()) {
                const data = await this._post(
                    `/sessions/${this.sessionId}/instruction`,
                    { text: prompt }
                );
                if (data && data.plan) {
                    this.currentPlan = data.plan;
                    this.currentStepIndex = data.current_step_index || 0;
                    this._setStatus(
                        `✅ ${data.plan.title}（共 ${data.plan.steps.length} 步）`);
                    this._showPanel(true);
                    this._renderStep();
                    return;
                }
            }

            // ---- 后端不可用 → 本地兜底导览 ----
            this._localPlan(st);
        } finally {
            this._busy = false;
        }
    },

    // ============================================================
    //  五、本地兜底导览（无 AI 后端也能用）
    // ============================================================

    _localPlan(st) {
        const steps = [];
        const push = o => { o.step_index = steps.length; steps.push(o); };

        // ---- 1. 行星 / 月球 ----
        for (const p of st.planets.slice(0, 3)) {
            push({
                title: p.zh,
                narration: {
                    long: `${p.zh}此刻位于地平线上方约 ${p.alt.toFixed(0)}°，` +
                          `方位 ${p.az.toFixed(0)}°` +
                          (p.mag != null ? `，视星等约 ${p.mag} 等` : "") +
                          `，是当前天空中最值得优先关注的目标之一。`,
                    best_time: "此刻即可观测",
                    observation_tip: "肉眼即可定位；双筒望远镜或小口径望远镜能看到更多细节。",
                    fun_fact: SOLAR_FACT[p.key] || ""
                },
                targets: [{
                    name_en: p.key, name_zh: p.zh,
                    ra_deg: p.ra, dec_deg: p.dec,
                    magnitude: p.mag, constellation: "太阳系", altitude_deg: p.alt
                }],
                camera: { center_ra_deg: p.ra, center_dec_deg: p.dec, fov_deg: 30 }
            });
        }

        // ---- 2. 星座 ----
        for (const c of st.constellations.slice(0, 5)) {
            push({
                title: c.zh,
                narration: {
                    long: `${c.zh}目前位于地平线以上，最高约 ${c.maxAlt.toFixed(0)}°，` +
                          `共有 ${c.notable} 颗亮于 3.5 等的恒星可见，` +
                          `其中最亮的是 ${c.brightest.name}（${c.brightest.mag} 等）。`,
                    best_time: "当前时段",
                    observation_tip: "先用肉眼辨认整体轮廓，再用双筒望远镜扫视其中的亮星。"
                },
                targets: c.stars.map(s => ({
                    name_en: s.name, name_zh: "",
                    ra_deg: s.ra_hours * 15, dec_deg: s.dec,
                    magnitude: s.mag, constellation: c.zh, altitude_deg: s.alt
                })),
                camera: { center_ra_deg: c.centerRa, center_dec_deg: c.centerDec, fov_deg: 45 }
            });
        }

        // ---- 3. 深空天体 ----
        for (const d of st.dsos.slice(0, 3)) {
            push({
                title: `${d.name}（深空天体）`,
                narration: {
                    long: `${d.name} 现在高度约 ${d.alt.toFixed(0)}°，视星等 ${d.mag} 等` +
                          (d.dim ? `，视面大小约 ${d.dim} 角分` : "") + "。",
                    observation_tip: "需要双筒望远镜或天文望远镜，并尽量避开城市灯光。"
                },
                targets: [{
                    name_en: d.name, name_zh: "",
                    ra_deg: d.ra, dec_deg: d.dec,
                    magnitude: d.mag, constellation: "深空", altitude_deg: d.alt
                }],
                camera: { center_ra_deg: d.ra, center_dec_deg: d.dec, fov_deg: 20 }
            });
        }

        // ---- 4. 完全无目标 ----
        if (!steps.length) {
            push({
                title: "今晚星空概况",
                narration: {
                    long: "当前时刻地平线上方没有明显的亮星、行星或深空天体，" +
                          "可能仍处于白天或天气条件不佳。建议稍晚些时候再观测。"
                },
                targets: [],
                camera: null
            });
        }

        this.currentPlan = { title: `${st.timeStr} 实时星空导览`, steps };
        this.currentStepIndex = 0;
        this._showPanel(true);
        this._renderStep();
        this._setStatus(`✅ 已生成 ${steps.length} 步本地导览（AI 后端未连接）`);
    },

    // ============================================================
    //  六、步骤控制
    // ============================================================

    async next() {
        if (!this.sessionId || !this.currentPlan) { this._stepLocal(1); return; }
        const data = await this._post(`/sessions/${this.sessionId}/next`);
        if (!data) { this._stepLocal(1); return; }
        if (data.status === "finished") { this._setStatus("漫游完成 🎉"); return; }
        if (data.status === "stopped") { this._setStatus("会话已停止"); return; }
        if (data.status === "no_plan") { this._setStatus("尚未生成路线", true); return; }
        if (typeof data.current_step_index === "number") {
            this.currentStepIndex = data.current_step_index;
        }
        this._renderStep();
    },

    async prev() {
        if (!this.sessionId || !this.currentPlan) { this._stepLocal(-1); return; }
        const data = await this._post(`/sessions/${this.sessionId}/prev`);
        if (!data) { this._stepLocal(-1); return; }
        if (data.status === "at_first_step") { this._setStatus("已经是第一步了"); return; }
        if (data.status === "stopped") { this._setStatus("会话已停止"); return; }
        if (typeof data.current_step_index === "number") {
            this.currentStepIndex = data.current_step_index;
        }
        this._renderStep();
    },

    /** 本地兜底时的步进 */
    _stepLocal(delta) {
        if (!this.currentPlan) return;
        const n = this.currentPlan.steps.length;
        const i = this.currentStepIndex + delta;
        if (i < 0) { this._setStatus("已经是第一步了"); return; }
        if (i >= n) { this._setStatus("漫游完成 🎉"); return; }
        this.currentStepIndex = i;
        this._renderStep();
    },

    async pause() {
        if (!this.sessionId) { this._setStatus("（本地导览，无会话可暂停）"); return; }
        const data = await this._post(`/sessions/${this.sessionId}/pause`);
        if (!data) return;
        this._setStatus(`已暂停（第 ${(data.current_step_index ?? 0) + 1} 步）`);
    },

    async stop() {
        if (this.sessionId) await this._post(`/sessions/${this.sessionId}/stop`);
        this.sessionId = null;
        this.currentPlan = null;
        this.currentStepIndex = 0;
        this._setStatus("已停止漫游");
        this._showPanel(false);
    },

    // ============================================================
    //  七、目标定位（与搜索模式一致）
    // ============================================================

    _navigateToTarget(target) {
        if (!target) return;
        const scene = window.celestialScene;
        if (!scene) { this._setStatus("星图场景未加载", true); return; }

        // 策略1：深空天体
        if (target.name_en && scene.dsoData) {
            const dso = scene.dsoData.find(d => d.name === target.name_en);
            if (dso) {
                scene.focusOnStar(dso);
                if (scene.showDSOInfo) scene.showDSOInfo(dso);
                this._setStatus(`已定位到 ${dso.name}`);
                return;
            }
        }

        // 策略2：恒星（英文名）
        let star = null;
        if (target.name_en && scene.starData) {
            star = scene.starData.find(s => s.name === target.name_en);
        }
        // 策略3：恒星（中文名）
        if (!star && target.name_zh && scene.starData) {
            star = scene.starData.find(s => s.name === target.name_zh);
        }
        // 策略4：坐标就近匹配（容差 0.5°）
        if (!star && target.ra_deg != null && target.dec_deg != null && scene.starData) {
            star = scene.starData.find(s => {
                if (s.ra_hours == null || s.dec == null) return false;
                return Math.abs(s.ra_hours * 15 - target.ra_deg) < 0.5 &&
                       Math.abs(s.dec - target.dec_deg) < 0.5;
            });
        }
        // 策略5：太阳系天体（按名称）
        if (!star && scene.focusOnSolarBody && target.name_en) {
            const solarNames = ["Sun", "Moon", "Mercury", "Venus", "Mars",
                                "Jupiter", "Saturn", "Uranus", "Neptune"];
            if (solarNames.includes(target.name_en)) {
                scene.focusOnSolarBody(target.name_en);
                if (scene.showSolarInfo) scene.showSolarInfo(target.name_en);
                this._setStatus(`已定位到 ${target.name_zh || target.name_en}`);
                return;
            }
        }

        if (star) {
            scene.focusOnStar(star);
            if (scene.showStarInfo) scene.showStarInfo(star);
        } else if (target.ra_deg != null && target.dec_deg != null) {
            // 策略6：直接按坐标飞行
            if (scene.lookAtRaDec) scene.lookAtRaDec(target.ra_deg, target.dec_deg, 1000);
        }
        this._setStatus(`已定位到 ${target.name_zh || target.name_en || "目标"}`);
    },

    // ============================================================
    //  八、渲染
    // ============================================================

    _showPanel(show) {
        const p = document.getElementById("tour-panel");
        if (p) p.style.display = show ? "block" : "none";
    },

    _renderStep() {
        if (!this.currentPlan) return;
        const steps = this.currentPlan.steps || [];
        const step = steps[this.currentStepIndex];
        if (!step) return;

        const titleEl = document.getElementById("tour-title");
        if (titleEl) {
            titleEl.textContent = `${step.step_index + 1}/${steps.length} · ${step.title}`;
        }

        const narr = step.narration || {};
        let html = "";
        html += `<p class="narr-long">${narr.long || narr.short || ""}</p>`;
        if (narr.best_time) {
            html += `<p class="narr-best-time">🕐 最佳观测：${narr.best_time}</p>`;
        }
        if (narr.cultural_story) {
            html += `<div class="narr-culture"><span class="narr-label">📖 典故</span>` +
                    `<p>${narr.cultural_story}</p></div>`;
        }
        if (narr.observation_tip) {
            html += `<p class="narr-tip">🔭 ${narr.observation_tip}</p>`;
        }
        if (narr.fun_fact) {
            html += `<p class="narr-fun">💡 ${narr.fun_fact}</p>`;
        }
        const narrEl = document.getElementById("tour-narration");
        if (narrEl) narrEl.innerHTML = html;

        this._renderTargets(step);
        this._applyCamera(step);
        this._showPanel(true);
    },

    _renderTargets(step) {
        const container = document.getElementById("tour-targets");
        if (!container) return;

        const targets = step.targets || [];
        if (!targets.length) { container.innerHTML = ""; return; }

        container.innerHTML = targets.map((t, i) => {
            const name = t.name_zh || t.name_en || `目标 ${i + 1}`;
            const magText = t.magnitude != null ? `mag ${Number(t.magnitude).toFixed(1)}` : "";
            const altText = t.altitude_deg != null ? `高度 ${Number(t.altitude_deg).toFixed(0)}°` : "";
            const meta = [t.constellation, magText, altText].filter(Boolean).join(" · ");
            return `
                <div class="tour-target-item" data-index="${i}">
                    <div class="tour-target-info">
                        <span class="tour-target-name">${name}</span>
                        <span class="tour-target-meta">${meta}</span>
                    </div>
                    <button class="tour-navigate-btn" data-index="${i}" title="定位到这颗星">🧭 定位</button>
                </div>`;
        }).join("");

        container.querySelectorAll(".tour-navigate-btn").forEach(btn => {
            btn.addEventListener("click", e => {
                e.stopPropagation();
                const t = targets[parseInt(btn.dataset.index, 10)];
                if (t) this._navigateToTarget(t);
            });
        });
        container.querySelectorAll(".tour-target-item").forEach(item => {
            item.addEventListener("click", () => {
                const t = targets[parseInt(item.dataset.index, 10)];
                if (t) this._navigateToTarget(t);
            });
        });
    },

    /** 相机联动（修正：第三个参数是动画时长，FOV 单独设置） */
    _applyCamera(step) {
        const cam = step.camera;
        if (!cam) return;
        const scene = window.celestialScene;
        if (!scene) return;

        const ra = cam.center_ra_deg;
        const dec = cam.center_dec_deg;
        if (ra == null || dec == null) return;

        if (typeof scene.lookAtRaDec === "function") {
            scene.lookAtRaDec(ra, dec, cam.duration || 1200);
        } else if (typeof scene.focusOnStar === "function") {
            scene.focusOnStar({ ra_hours: ra / 15, dec: dec, name: "" });
        }

        if (cam.fov_deg && scene.camera) {
            scene.camera.fov = Math.max(
                scene.fovMin || 4,
                Math.min(scene.fovMax || 110, cam.fov_deg)
            );
            scene.camera.updateProjectionMatrix();
            if (scene._updateStarSizes) scene._updateStarSizes();
            if (scene._applyLabelLOD) scene._applyLabelLOD();
            const ind = document.getElementById("fov-indicator");
            if (ind) {
                ind.textContent = `FOV: ${scene.camera.fov.toFixed(0)}°`;
                ind.style.display = "block";
            }
        }
    },
};

// ============================================================
//  九、静态查表
// ============================================================

/** 星座三字母缩写 → 简体中文名 */
const CON_ZH = {
    And:"仙女座", Ant:"唧筒座", Aps:"天燕座", Aqr:"宝瓶座", Aql:"天鹰座",
    Ara:"天坛座", Ari:"白羊座", Aur:"御夫座", Boo:"牧夫座", Cae:"雕具座",
    Cam:"鹿豹座", Cnc:"巨蟹座", CVn:"猎犬座", CMa:"大犬座", CMi:"小犬座",
    Cap:"摩羯座", Car:"船底座", Cas:"仙后座", Cen:"半人马座", Cep:"仙王座",
    Cet:"鲸鱼座", Cha:"蝘蜓座", Cir:"圆规座", Col:"天鸽座", Com:"后发座",
    CrA:"南冕座", CrB:"北冕座", Crv:"乌鸦座", Crt:"巨爵座", Cru:"南十字座",
    Cyg:"天鹅座", Del:"海豚座", Dor:"剑鱼座", Dra:"天龙座", Equ:"小马座",
    Eri:"波江座", For:"天炉座", Gem:"双子座", Gru:"天鹤座", Her:"武仙座",
    Hor:"时钟座", Hya:"长蛇座", Hyi:"水蛇座", Ind:"印第安座", Lac:"蝎虎座",
    Leo:"狮子座", LMi:"小狮座", Lep:"天兔座", Lib:"天秤座", Lup:"豺狼座",
    Lyn:"天猫座", Lyr:"天琴座", Men:"山案座", Mic:"显微镜座", Mon:"麒麟座",
    Mus:"苍蝇座", Nor:"矩尺座", Oct:"南极座", Oph:"蛇夫座", Ori:"猎户座",
    Pav:"孔雀座", Peg:"飞马座", Per:"英仙座", Phe:"凤凰座", Pic:"绘架座",
    Psc:"双鱼座", PsA:"南鱼座", Pup:"船尾座", Pyx:"罗盘座", Ret:"网罟座",
    Sge:"天箭座", Sgr:"人马座", Sco:"天蝎座", Scl:"玉夫座", Sct:"盾牌座",
    Ser:"巨蛇座", Sex:"六分仪座", Tau:"金牛座", Tel:"望远镜座", Tri:"三角座",
    TrA:"南三角座", Tuc:"杜鹃座", UMa:"大熊座", UMi:"小熊座", Vel:"船帆座",
    Vir:"室女座", Vol:"飞鱼座", Vul:"狐狸座"
};

const SOLAR_ZH = {
    Sun:"太阳", Moon:"月球", Mercury:"水星", Venus:"金星", Mars:"火星",
    Jupiter:"木星", Saturn:"土星", Uranus:"天王星", Neptune:"海王星"
};

const SOLAR_FACT = {
    Sun: "太阳是太阳系唯一的恒星，直径约 139 万公里。",
    Moon: "月球是地球唯一的天然卫星，距离约 38 万公里，环形山用双筒即可看清。",
    Mercury: "水星离太阳最近，只在日出前或日落后很短的时间里露面。",
    Venus: "金星是夜空中最亮的行星，浓密的硫酸云使它反射率极高。",
    Mars: "火星表面呈现明显的橙红色，源自土壤中的氧化铁。",
    Jupiter: "木星是太阳系最大的行星，4 颗伽利略卫星用双筒就能看到。",
    Saturn: "土星环是最壮观的太阳系景观，小口径望远镜即可分辨。",
    Uranus: "天王星呈淡蓝绿色，是唯一「躺着自转」的行星。",
    Neptune: "海王星是距太阳最远的行星，需要用望远镜才能看到。"
};

// ============================================================
//  十、UI 绑定（无用户输入）
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    const autoBtn = document.getElementById("tour-auto");
    if (autoBtn) autoBtn.addEventListener("click", () => Tour.autoStart());

    document.getElementById("tour-next")?.addEventListener("click", () => Tour.next());
    document.getElementById("tour-prev")?.addEventListener("click", () => Tour.prev());
    document.getElementById("tour-pause")?.addEventListener("click", () => Tour.pause());
    document.getElementById("tour-stop")?.addEventListener("click", () => Tour.stop());
});