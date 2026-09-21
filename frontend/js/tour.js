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

        if (data.status === "finished") {
            this._setStatus("漫游完成 🎉");
            return;
        }
        if (data.status === "stopped") {
            this._setStatus("会话已停止");
            return;
        }
        if (data.status === "no_plan") {
            this._setStatus("尚未生成路线", true);
            return;
        }
        if (typeof data.current_step_index === "number") {
            this.currentStepIndex = data.current_step_index;
        }
        this._renderStep();
    },

    async prev() {
        if (!this.sessionId) return;
        const data = await this._post(`/sessions/${this.sessionId}/prev`);
        if (!data) return;

        if (data.status === "at_first_step") {
            this._setStatus("已经是第一步了");
            return;
        }
        if (data.status === "stopped") {
            this._setStatus("会话已停止");
            return;
        }
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

        document.getElementById("tour-title").textContent =
            `${step.step_index + 1}/${steps.length} · ${step.title}`;

        const narr =
            (step.narration && (step.narration.long || step.narration.short)) || "";
        document.getElementById("tour-narration").textContent = narr;

        this._applyCamera(step);
        this._showPanel(true);
    },

    // 探测式相机联动（不同版本 scene3d.js 暴露的名字可能不同）
    _applyCamera(step) {
        const cam = step.camera;
        if (!cam) return;

        const candidates = [
            window.scene3d, window.Scene3D, window.Sky3D, window.celestial,
        ];

        for (const obj of candidates) {
            if (!obj) continue;
            if (typeof obj.flyTo === "function") {
                try {
                    obj.flyTo(cam.center_ra_deg, cam.center_dec_deg, cam.fov_deg);
                    return;
                } catch (e) {
                    console.warn("[Tour] flyTo 失败", e);
                }
            }
            if (typeof obj.lookAtRaDec === "function") {
                try {
                    obj.lookAtRaDec(cam.center_ra_deg, cam.center_dec_deg, cam.fov_deg);
                    return;
                } catch (e) {
                    console.warn("[Tour] lookAtRaDec 失败", e);
                }
            }
        }
        // 没找到任何接口就静默跳过，文字导览仍可正常工作
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