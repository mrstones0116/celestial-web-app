const Tour = {
  sessionId: null,
  currentPlan: null,
  currentStepIndex: 0,
  apiBase: "/api/tour",

  // -------- 内部工具 --------
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
      console.error("[Tour] 网络错误", e);
      this._setStatus("网络请求失败，请检查后端是否运行", true);
      return null;
    }
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      console.error("[Tour] HTTP", res.status, text);
      this._setStatus(`后端错误 ${res.status}`, true);
      return null;
    }
    try {
      return await res.json();
    } catch (e) {
      console.error("[Tour] JSON 解析失败", e);
      this._setStatus("后端返回格式异常", true);
      return null;
    }
  },

  // -------- 会话 --------
  async _ensureSession() {
    if (this.sessionId) return true;
    const data = await this._post("/sessions", {});
    if (!data || !data.session_id) return false;
    this.sessionId = data.session_id;
    return true;
  },

  // -------- 对外 API --------
  async start(text) {
    text = (text || "").trim();
    if (!text) {
      this._setStatus("请输入一句话，例如：我想看夏季星空", true);
      return;
    }
    this._setStatus("正在生成路线...");
    if (!(await this._ensureSession())) return;

    const data = await this._post(
      `/sessions/${this.sessionId}/instruction`,
      { text }
    );
    if (!data) return;

    if (data.status === "stopped") {
      this._setStatus("会话已停止", true);
      return;
    }
    if (!data.plan) {
      this._setStatus("后端未返回路线", true);
      return;
    }

    this.currentPlan = data.plan;
    this.currentStepIndex = data.current_step_index || 0;
    this._setStatus(`已生成：${data.plan.title}（共 ${data.plan.steps.length} 步）`);
    this._showPanel(true);
    this._renderStep();
  },

  async next() {
    if (!this.sessionId) return;
    const data = await this._post(`/sessions/${this.sessionId}/next`);
    if (!data) return;
    if (data.status === "finished") { this._setStatus("漫游完成 🎉"); return; }
    if (data.status === "stopped") { this._setStatus("会话已停止"); return; }
    if (data.status === "no_plan") { this._setStatus("尚未生成路线", true); return; }
    if (typeof data.current_step_index === "number") {
      this.currentStepIndex = data.current_step_index;
    }
    this._renderStep();
  },

  async prev() {
    if (!this.sessionId) return;
    const data = await this._post(`/sessions/${this.sessionId}/prev`);
    if (!data) return;
    if (data.status === "at_first_step") { this._setStatus("已经是第一步了"); return; }
    if (data.status === "stopped") { this._setStatus("会话已停止"); return; }
    if (typeof data.current_step_index === "number") {
      this.currentStepIndex = data.current_step_index;
    }
    this._renderStep();
  },

  async pause() {
    if (!this.sessionId) return;
    const data = await this._post(`/sessions/${this.sessionId}/pause`);
    if (!data) return;
    this._setStatus(`已暂停（第 ${(data.current_step_index ?? 0) + 1} 步）`);
  },

  async stop() {
    if (this.sessionId) {
      await this._post(`/sessions/${this.sessionId}/stop`);
    }
    this.sessionId = null;
    this.currentPlan = null;
    this.currentStepIndex = 0;
    this._setStatus("已停止漫游");
    this._showPanel(false);
  },

  // -------- ✅ 新增：定位到某颗星（与搜索模式一致） --------
  _navigateToTarget(target) {
    if (!target) return;

    const scene = window.celestialScene;
    if (!scene) {
      this._setStatus("星图场景未加载", true);
      return;
    }

    // 策略1：通过英文名在星表数据中查找（与 search.js 一致）
    let star = null;
    if (target.name_en && scene.starData) {
      star = scene.starData.find(s => s.name === target.name_en);
    }

    // 策略2：通过中文名匹配
    if (!star && target.name_zh && scene.starData) {
      star = scene.starData.find(s => s.name === target.name_zh);
    }

    // 策略3：通过坐标就近匹配（容差 0.5°）
    if (!star && target.ra_deg != null && target.dec_deg != null && scene.starData) {
      const tolerance = 0.5;
      star = scene.starData.find(s => {
        if (s.ra_hours == null || s.dec == null) return false;
        const sRaDeg = s.ra_hours * 15;
        return Math.abs(sRaDeg - target.ra_deg) < tolerance &&
               Math.abs(s.dec - target.dec_deg) < tolerance;
      });
    }

    if (star) {
      scene.focusOnStar(star);
      if (scene.showStarInfo) scene.showStarInfo(star);
      if (scene._onClickFocusStar) scene._onClickFocusStar(star);
    } else {
      // 策略4：直接用坐标飞行（不依赖星表查找）
      this._flyToRaDec(target.ra_deg, target.dec_deg);
    }

    this._setStatus(`已定位到 ${target.name_zh || target.name_en || "目标"}`);
  },

  _flyToRaDec(raDeg, decDeg, fov = 25) {
    if (raDeg == null || decDeg == null) return;

    const candidates = [
      window.celestialScene,
      window.scene3d, window.Scene3D, window.Sky3D, window.celestial,
    ];
    for (const obj of candidates) {
      if (!obj) continue;
      if (typeof obj.flyTo === "function") {
        try { obj.flyTo(raDeg, decDeg, fov); return; } catch (e) { /* continue */ }
      }
      if (typeof obj.lookAtRaDec === "function") {
        try { obj.lookAtRaDec(raDeg, decDeg, fov); return; } catch (e) { /* continue */ }
      }
      if (typeof obj.focusOnStar === "function") {
        // 构造一个临时 star 对象
        try {
          obj.focusOnStar({ ra_hours: raDeg / 15, dec: decDeg, name: "" });
          return;
        } catch (e) { /* continue */ }
      }
    }
    console.warn("[Tour] 未找到可用的相机控制接口");
  },

  // -------- 渲染 --------
  _showPanel(show) {
    const p = document.getElementById("tour-panel");
    if (p) p.style.display = show ? "block" : "none";
  },

  _renderStep() {
    if (!this.currentPlan) return;
    const steps = this.currentPlan.steps || [];
    const step = steps[this.currentStepIndex];
    if (!step) return;

    // 标题
    document.getElementById("tour-title").textContent =
      `${step.step_index + 1}/${steps.length} · ${step.title}`;

    // 解说
    const narr =
      (step.narration && (step.narration.long || step.narration.short)) || "";
    document.getElementById("tour-narration").textContent = narr;

    // ✅ 新增：渲染目标星列表 + Navigate 按钮
    this._renderTargets(step);

    // 自动切换视角（保持原有行为）
    this._applyCamera(step);
    this._showPanel(true);
  },

  // ✅ 新增：渲染每颗目标星 + 导航按钮
  _renderTargets(step) {
    const container = document.getElementById("tour-targets");
    if (!container) return;

    const targets = step.targets || [];
    if (targets.length === 0) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = targets.map((t, i) => {
      const name = t.name_zh || t.name_en || `目标 ${i + 1}`;
      const magText = t.magnitude != null ? `mag ${t.magnitude.toFixed(1)}` : "";
      const altText = t.altitude_deg != null ? `高度 ${t.altitude_deg.toFixed(0)}°` : "";
      const constText = t.constellation || "";
      const meta = [constText, magText, altText].filter(Boolean).join(" · ");

      return `
        <div class="tour-target-item" data-index="${i}">
          <div class="tour-target-info">
            <span class="tour-target-name">${name}</span>
            <span class="tour-target-meta">${meta}</span>
          </div>
          <button class="tour-navigate-btn" data-index="${i}" title="定位到这颗星">
            🧭 定位
          </button>
        </div>
      `;
    }).join("");

    // 绑定点击事件
    container.querySelectorAll(".tour-navigate-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.dataset.index, 10);
        const target = targets[idx];
        if (target) this._navigateToTarget(target);
      });
    });

    // 点击整行也可以定位
    container.querySelectorAll(".tour-target-item").forEach(item => {
      item.addEventListener("click", () => {
        const idx = parseInt(item.dataset.index, 10);
        const target = targets[idx];
        if (target) this._navigateToTarget(target);
      });
    });
  },

  // 相机联动
  _applyCamera(step) {
    const cam = step.camera;
    if (!cam) return;

    const candidates = [
      window.celestialScene,
      window.scene3d, window.Scene3D, window.Sky3D, window.celestial,
    ];
    for (const obj of candidates) {
      if (!obj) continue;
      if (typeof obj.flyTo === "function") {
        try { obj.flyTo(cam.center_ra_deg, cam.center_dec_deg, cam.fov_deg); return; } catch (e) {}
      }
      if (typeof obj.lookAtRaDec === "function") {
        try { obj.lookAtRaDec(cam.center_ra_deg, cam.center_dec_deg, cam.fov_deg); return; } catch (e) {}
      }
    }
  },
};

// -------- UI 绑定 --------
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("tour-input");
  const startBtn = document.getElementById("tour-start");
  if (startBtn) {
    startBtn.addEventListener("click", () => Tour.start(input?.value));
  }
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") Tour.start(input.value);
    });
  }
  document.getElementById("tour-next")?.addEventListener("click", () => Tour.next());
  document.getElementById("tour-prev")?.addEventListener("click", () => Tour.prev());
  document.getElementById("tour-pause")?.addEventListener("click", () => Tour.pause());
  document.getElementById("tour-stop")?.addEventListener("click", () => Tour.stop());
});