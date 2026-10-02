"""星座目录：HYG 成员星 + 前端 GeoJSON 骨架线。

成员星加载依赖 loader.df，所以不在 __init__ 里自动加载，
改成显式 load()，由 server.py 的 startup 钩子在星表就绪后调用。
"""
import json
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_FRONTEND_DIR = _BACKEND_DIR.parent / "frontend"

_CN_NAMES = {
    "And": "仙女座", "Ant": "唧筒座", "Aps": "天燕座",
    "Aqr": "宝瓶座", "Aql": "天鹰座", "Ara": "天坛座",
    "Ari": "白羊座", "Aur": "御夫座", "Boo": "牧夫座",
    "Cae": "雕具座", "Cam": "鹿豹座", "Cnc": "巨蟹座",
    "CMa": "大犬座", "CMi": "小犬座", "Cap": "摩羯座",
    "Car": "船底座", "Cas": "仙后座", "Cen": "半人马座",
    "Cep": "仙王座", "Cet": "鲸鱼座", "Cha": "蝘蜓座",
    "Cir": "圆规座", "Col": "天鸽座", "Com": "后发座",
    "CrA": "南冕座", "CrB": "北冕座", "Crv": "乌鸦座",
    "Crt": "巨爵座", "Cru": "南十字座", "Cyg": "天鹅座",
    "Del": "海豚座", "Dor": "剑鱼座", "Dra": "天龙座",
    "Equ": "小马座", "Eri": "波江座", "For": "天炉座",
    "Gem": "双子座", "Gru": "天鹤座", "Her": "武仙座",
    "Hor": "时钟座", "Hya": "长蛇座", "Hyi": "水蛇座",
    "Ind": "印第安座", "Lac": "蝎虎座", "Leo": "狮子座",
    "LMi": "小狮座", "Lep": "天兔座", "Lib": "天秤座",
    "Lup": "豺狼座", "Lyn": "天猫座", "Lyr": "天琴座",
    "Men": "山案座", "Mic": "显微镜座", "Mon": "麒麟座",
    "Mus": "苍蝇座", "Nor": "矩尺座", "Oct": "南极座",
    "Oph": "蛇夫座", "Ori": "猎户座", "Peg": "飞马座",
    "Per": "英仙座", "Phe": "凤凰座", "Pic": "绘架座",
    "Psc": "双鱼座", "PsA": "南鱼座", "Pup": "船尾座",
    "Pyx": "罗盘座", "Ret": "网罟座", "Sge": "天箭座",
    "Sgr": "人马座", "Sco": "天蝎座", "Scl": "玉夫座",
    "Sct": "盾牌座", "Ser": "巨蛇座", "Sex": "六分仪座",
    "Tau": "金牛座", "Tel": "望远镜座", "Tri": "三角座",
    "TrA": "南三角座", "Tuc": "杜鹃座", "UMa": "大熊座",
    "UMi": "小熊座", "Vel": "船帆座", "Vir": "室女座",
    "Vol": "飞鱼座", "Vul": "狐狸座",
}


def _safe_str(v) -> str:
    """把 pandas NaN / None / NA / NaT 都转成空串。"""
    if v is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = str(v).strip()
    if s.lower() in ("nan", "none", "<na>", "nat", "null"):
        return ""
    return s


class ConstellationCatalog:
    """从 HYG 取成员星，从前端 GeoJSON 取骨架线。"""

    def __init__(self, loader, max_mag: float = 5.0):
        self.loader = loader
        self.max_mag = max_mag
        self._members: Dict[str, List[Dict[str, Any]]] = {}
        self._lines: Dict[str, List[List[List[float]]]] = {}
        self._members_loaded = False
        self._lines_loaded = False

    # ---------- 显式加载 ----------

    def load(self):
        """由 server.py 的 startup 钩子在 loader.load_data() 之后调用。"""
        self.load_lines()
        self.load_members()

    # ---------- 骨架线（不依赖 loader.df） ----------

    def load_lines(self):
        if self._lines_loaded:
            return
        candidates = [
            _FRONTEND_DIR / "data" / "constellations.lines.json",
            _BACKEND_DIR / "data" / "constellations.lines.json",
            _BACKEND_DIR.parent / "frontend" / "data" / "constellations.lines.json",
            Path.cwd() / "frontend" / "data" / "constellations.lines.json",
            Path.cwd() / "data" / "constellations.lines.json",
        ]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            print("⚠️ catalog: 找不到 constellations.lines.json")
            return

        print(f"📚 catalog: 加载骨架线: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ catalog: 骨架 JSON 读取失败: {e}")
            return

        feats = data.get("features") if isinstance(data, dict) else None
        if not isinstance(feats, list):
            print("⚠️ catalog: 骨架 JSON 无 features 数组")
            return

        n_lines_total = 0
        for feat in feats:
            if not isinstance(feat, dict):
                continue
            props = feat.get("properties") or {}
            abbr = str(
                props.get("id") or props.get("abbr")
                or feat.get("id") or ""
            ).strip()
            if not abbr:
                continue

            geom = feat.get("geometry") or {}
            gtype = geom.get("type")
            coords = geom.get("coordinates")
            lines: List[List[List[float]]] = []

            def _norm_pt(pt):
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    return None
                try:
                    ra = float(pt[0]) % 360.0
                    dec = float(pt[1])
                except (TypeError, ValueError):
                    return None
                return [ra, dec]

            if gtype == "MultiLineString" and isinstance(coords, list):
                for line in coords:
                    if not isinstance(line, list):
                        continue
                    pts = [p for p in (_norm_pt(x) for x in line)
                           if p is not None]
                    if len(pts) >= 2:
                        lines.append(pts)
            elif gtype == "LineString" and isinstance(coords, list):
                pts = [p for p in (_norm_pt(x) for x in coords)
                       if p is not None]
                if len(pts) >= 2:
                    lines.append(pts)

            if lines:
                self._lines[abbr] = lines
                n_lines_total += len(lines)

        print(f"📚 catalog: 加载 {len(self._lines)} 个星座骨架，"
              f"共 {n_lines_total} 条线")
        self._lines_loaded = True

    # ---------- 成员星（依赖 loader.df） ----------

    def load_members(self):
        if self._members_loaded:
            return

        df = self.loader.df
        if df is None:
            print("⚠️ catalog: loader.df 为 None，成员星暂不加载")
            return

        con_col = "con"
        if con_col not in df.columns:
            print("⚠️ catalog: df 无 'con' 列")
            return

        ra_col = "ra_deg" if "ra_deg" in df.columns else "ra"
        ra_scale = 1.0 if ra_col == "ra_deg" else 15.0
        print(f"📚 catalog: 成员星列 ra='{ra_col}' (scale={ra_scale}), "
              f"mag<{self.max_mag}")

        try:
            mags = df["mag"].astype(float)
        except Exception as e:
            print(f"⚠️ catalog: mag 列转换失败: {e}")
            return

        mask = df[con_col].notna() & (mags < self.max_mag)
        sub = df[mask]

        n_total = 0
        n_proper = 0
        n_bf_only = 0

        for abbr, group in sub.groupby(con_col):
            abbr = str(abbr).strip()
            if not abbr or abbr == "nan":
                continue

            rows: List[Dict[str, Any]] = []
            for _, row in group.iterrows():
                try:
                    ra = float(row[ra_col]) * ra_scale
                    dec = float(row["dec"])
                    mag = float(row["mag"])
                except (TypeError, ValueError, KeyError):
                    continue

                # 星名：优先 proper，没有则 bf
                proper = _safe_str(row.get("proper"))
                bf = _safe_str(row.get("bf"))
                display = proper or bf

                if proper:
                    n_proper += 1
                elif bf:
                    n_bf_only += 1

                rows.append({
                    "name": proper,          # 传统星名（可能为空）
                    "bf": bf,                # Bayer/Flamsteed 编号
                    "display_name": display,  # 用于绘制标签的最终星名
                    "ra": ra,
                    "dec": dec,
                    "mag": mag,
                    "hr": _safe_str(row.get("hr")),
                })

            if rows:
                rows.sort(key=lambda r: r["mag"])
                self._members[abbr] = rows
                n_total += len(rows)

        print(f"📚 catalog: 加载 {len(self._members)} 个星座成员表，"
              f"共 {n_total} 颗星"
              f"（proper={n_proper}, bf-only={n_bf_only}）")
        self._members_loaded = True

    # ---------- 查询（惰性触发） ----------

    def _ensure(self):
        if not self._lines_loaded:
            self.load_lines()
        if not self._members_loaded:
            self.load_members()

    def get_members(self, abbr: str) -> List[Dict[str, Any]]:
        self._ensure()
        return list(self._members.get(abbr, []))

    def get_lines(self, abbr: str) -> List[List[List[float]]]:
        self._ensure()
        return list(self._lines.get(abbr, []))

    def get_cn_name(self, abbr: str) -> str:
        return _CN_NAMES.get(abbr, "")

    def has(self, abbr: str) -> bool:
        self._ensure()
        return abbr in self._members or abbr in self._lines

    def stats(self) -> Dict[str, int]:
        return {
            "members_constellations": len(self._members),
            "lines_constellations": len(self._lines),
            "members_loaded": self._members_loaded,
            "lines_loaded": self._lines_loaded,
        }