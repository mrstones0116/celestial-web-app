"""
星座识别器 —— 基于 astrometry.net 盲解算 (blind plate solving)
兼容 HYG loader 只返回 x/y/z 的极简字段。
"""
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

CONST_NAMES = {
    "And":"Andromeda","Ant":"Antlia","Aps":"Apus","Aqr":"Aquarius",
    "Aql":"Aquila","Ara":"Ara","Ari":"Aries","Aur":"Auriga",
    "Boo":"Boötes","Cae":"Caelum","Cam":"Camelopardalis","Cnc":"Cancer",
    "CVn":"Canes Venatici","CMa":"Canis Major","CMi":"Canis Minor",
    "Cap":"Capricornus","Car":"Carina","Cas":"Cassiopeia","Cen":"Centaurus",
    "Cep":"Cepheus","Cet":"Cetus","Cha":"Chamaeleon","Cir":"Circinus",
    "Col":"Columba","Com":"Coma Berenices","CrA":"Corona Australis",
    "CrB":"Corona Borealis","Crv":"Corvus","Crt":"Crater","Cru":"Crux",
    "Cyg":"Cygnus","Del":"Delphinus","Dor":"Dorado","Dra":"Draco",
    "Equ":"Equuleus","Eri":"Eridanus","For":"Fornax","Gem":"Gemini",
    "Gru":"Grus","Her":"Hercules","Hor":"Horologium","Hya":"Hydra",
    "Hyi":"Hydrus","Ind":"Indus","Lac":"Lacerta","Leo":"Leo",
    "LMi":"Leo Minor","Lep":"Lepus","Lib":"Libra","Lup":"Lupus",
    "Lyn":"Lynx","Lyr":"Lyra","Men":"Mensa","Mic":"Microscopium",
    "Mon":"Monoceros","Mus":"Musca","Nor":"Norma","Oct":"Octans",
    "Oph":"Ophiuchus","Ori":"Orion","Pav":"Pavo","Peg":"Pegasus",
    "Per":"Perseus","Phe":"Phoenix","Pic":"Pictor","Psc":"Pisces",
    "PsA":"Piscis Austrinus","Pup":"Puppis","Pyx":"Pyxis","Ret":"Reticulum",
    "Sge":"Sagitta","Sgr":"Sagittarius","Sco":"Scorpius","Scl":"Sculptor",
    "Sct":"Scutum","Ser":"Serpens","Sex":"Sextans","Tau":"Taurus",
    "Tel":"Telescopium","Tri":"Triangulum","TrA":"Triangulum Australe",
    "Tuc":"Tucana","UMa":"Ursa Major","UMi":"Ursa Minor","Vel":"Vela",
    "Vir":"Virgo","Vol":"Volans","Vul":"Vulpecula",
}


def _pick(d, *keys, default=None):
    for k in keys:
        if k in d:
            v = d[k]
            if v is None:
                continue
            if isinstance(v, float) and not np.isfinite(v):
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            return v
    return default


def _xyz_to_radec(x, y, z):
    """单位向量 (x,y,z) → (ra_hours, dec_deg)"""
    r = (x*x + y*y + z*z) ** 0.5
    if r <= 0:
        return None, None
    x, y, z = x/r, y/r, z/r
    ra_rad = np.arctan2(y, x)
    if ra_rad < 0:
        ra_rad += 2 * np.pi
    ra_hours = ra_rad * 12.0 / np.pi
    dec_deg = np.arcsin(np.clip(z, -1.0, 1.0)) * 180.0 / np.pi
    return float(ra_hours), float(dec_deg)


class ConstellationIdentifier:
    """基于 astrometry.net solve-field 的星座识别器。"""

    def __init__(
        self,
        hyg_stars: List[Dict],
        max_mag: float = 6.0,
        scale_low_arcsec: float = 0.5,
        scale_high_arcsec: float = 300.0,
        timeout: int = 180,
    ):
        self.max_mag = max_mag
        self.scale_low = scale_low_arcsec
        self.scale_high = scale_high_arcsec
        self.timeout = timeout

        # ---- 找 solve-field ----
        self.solve_field = shutil.which("solve-field")
        if not self.solve_field:
            for p in [
                r"C:\Users\Peter Stones\AppData\Local\cygwin_ansvr\bin\solve-field.bat",
                r"C:\Users\Peter Stones\AppData\Local\cygwin_ansvr\bin\solve-field",
            ]:
                if os.path.exists(p):
                    self.solve_field = p
                    break
        if self.solve_field:
            print(f"✅ 找到 solve-field: {self.solve_field}")
        else:
            print("⚠️ 未找到 solve-field")

        # ---- 构建 catalog（字段强兼容） ----
        self.catalog = []
        reasons = defaultdict(int)

        for s in hyg_stars:
            mag = _pick(s, "mag", "magnitude", "mag_v", "Vmag", "vmag")

            # 优先用 ra_hours/dec；否则从 x,y,z 反推
            ra  = _pick(s, "ra_hours", "ra_h", "ra_h", "ra")
            dec = _pick(s, "dec", "dec_deg", "de", "declination")
            if ra is None or dec is None:
                x = _pick(s, "x"); y = _pick(s, "y"); z = _pick(s, "z")
                if x is not None and y is not None and z is not None:
                    ra, dec = _xyz_to_radec(float(x), float(y), float(z))
                else:
                    reasons["no_coords"] += 1
                    continue

            if mag is None:
                reasons["no_mag"] += 1
                continue
            try:
                mag = float(mag); ra = float(ra); dec = float(dec)
            except (TypeError, ValueError):
                reasons["convert_fail"] += 1
                continue
            if not (np.isfinite(mag) and np.isfinite(ra) and np.isfinite(dec)):
                reasons["nonfinite"] += 1
                continue
            if ra > 24.0:
                ra = ra / 15.0
            if mag > max_mag:
                reasons["too_faint"] += 1
                continue

            self.catalog.append({
                "name": _pick(s, "name", "proper", "bf", "id", default=""),
                "ra_hours": ra,
                "dec": dec,
                "mag": mag,
                "constellation": _pick(s, "constellation", "con", "const", default=""),
                "spect": _pick(s, "spect", "spectral_type", default=None),
                "dist_ly": _pick(s, "dist_ly", "dist", default=None),
            })

        if not self.catalog:
            print(f"⚠️ 无亮星数据（输入 {len(hyg_stars)} 颗）")
            print(f"   跳过原因: {dict(reasons)}")
            if hyg_stars:
                print(f"   首颗字段: {list(hyg_stars[0].keys())}")
            self._ra_deg = np.empty(0)
            self._dec_deg = np.empty(0)
            self.has_constellation = False
        else:
            self._ra_deg = np.array([c["ra_hours"] for c in self.catalog]) * 15.0
            self._dec_deg = np.array([c["dec"] for c in self.catalog])
            self.has_constellation = any(c["constellation"] for c in self.catalog)
            print(f"✅ 识别器就绪：{len(self.catalog)} 颗星 "
                  f"(星座字段: {'有' if self.has_constellation else '无'})")
            print(f"   样本: {self.catalog[0]}")

    # ================================================================
    def identify(self, image_path: str, img_w: int, img_h: int,
                 top_n: int = 30) -> Optional[Dict]:
        if not self.solve_field or not self.catalog:
            print("⚠️ identify(): solve_field 或 catalog 为空")
            return None

        wcs = self._solve(image_path)
        if wcs is None:
            return None

        in_frame = self._project_catalog(wcs, img_w, img_h)
        print(f"   投影落在图像内的星: {len(in_frame)}")
        if not in_frame:
            return None

        # ---- 有星座字段：按星座分组；没有：直接返回最亮的 top_n ----
        if self.has_constellation:
            const_groups: Dict[str, List[Dict]] = defaultdict(list)
            for entry in in_frame:
                c = entry["constellation"]
                if c:
                    const_groups[c].append(entry)

            if not const_groups:
                return None

            def _score(c):
                grp = const_groups[c]
                return (len(grp), -min(s["mag"] for s in grp))

            best_const = max(const_groups.keys(), key=_score)
            members = sorted(const_groups[best_const], key=lambda s: s["mag"])
            if len(members) < 2:
                return None
            all_consts = {c: len(v) for c, v in sorted(
                const_groups.items(), key=lambda kv: -len(kv[1]))}
        else:
            # 无星座信息：直接返回图像内最亮的 N 颗
            members = sorted(in_frame, key=lambda s: s["mag"])[:top_n]
            best_const = "Unknown"
            all_consts = {"Unknown": len(in_frame)}

        result_stars = []
        for s in members[:top_n]:
            result_stars.append({
                "name": s["name"] or f"HIP star",
                "mag": s["mag"],
                "constellation": best_const,
                "px": round(s["px"], 1),
                "py": round(s["py"], 1),
                "ra_hours": s["ra_hours"],
                "dec": s["dec"],
                "spect": s.get("spect"),
                "dist_ly": s.get("dist_ly"),
            })

        confidence = min(1.0, len(members) / 8.0) * 0.7 + \
                     min(1.0, len(in_frame) / 20.0) * 0.3

        return {
            "constellation": best_const,
            "constellation_full": CONST_NAMES.get(best_const, best_const),
            "stars": result_stars,
            "confidence": round(confidence, 2),
            "total_matched": len(members),
            "all_constellations": all_consts,
            "wcs_center": {
                "ra_deg": float(wcs.wcs.crval[0]),
                "dec_deg": float(wcs.wcs.crval[1]),
            },
        }

    # ================================================================
    def _solve(self, image_path: str):
        try:
            from astropy.wcs import WCS
            from PIL import Image
        except ImportError as e:
            print(f"⚠️ 缺少依赖: {e}")
            return None

        work_dir = tempfile.mkdtemp(prefix="astrometry_")
        try:
            # solve-field 0.38 对 JPEG 支持差，先转 PNG 灰度
            png_path = os.path.join(work_dir, "input.png")
            try:
                Image.open(image_path).convert("L").save(png_path)
                print(f"[solve-field] 已转 PNG ({os.path.getsize(png_path)} 字节)")
            except Exception as e:
                print(f"⚠️ 图像预处理失败: {e}")
                return None

            cmd = [
                self.solve_field,
                "--overwrite", "--no-plots",
                "--dir", work_dir,
                "--scale-units", "arcsecperpix",
                "--scale-low", str(self.scale_low),
                "--scale-high", str(self.scale_high),
                "--downsample", "2",
                "--cpulimit", str(self.timeout),
                png_path,
            ]
            print(f"[solve-field] {' '.join(cmd)}")

            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout + 30, cwd=work_dir,
                encoding="utf-8", errors="replace",
            )
            print(f"[solve-field] 返回码: {proc.returncode}")

            if proc.stdout:
                for ln in proc.stdout.strip().splitlines()[-40:]:
                    print("   OUT |", ln)
            if proc.stderr:
                for ln in proc.stderr.strip().splitlines()[-20:]:
                    print("   ERR |", ln)

            wcs_path = os.path.join(work_dir, "input.wcs")
            if not os.path.exists(wcs_path):
                print(f"[solve-field] 未生成 WCS，工作目录内容: {os.listdir(work_dir)}")
                # 保存调试文件
                dbg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_solve_debug")
                os.makedirs(dbg, exist_ok=True)
                for f in os.listdir(work_dir):
                    try:
                        shutil.copy(os.path.join(work_dir, f), os.path.join(dbg, f))
                    except Exception:
                        pass
                print(f"[solve-field] 调试文件已保存: {dbg}")
                return None

            print(f"[solve-field] ✅ 解算成功")
            return WCS(wcs_path)

        except subprocess.TimeoutExpired:
            print("⚠️ solve-field 超时")
            return None
        except Exception:
            import traceback
            traceback.print_exc()
            return None
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ================================================================
    def _project_catalog(self, wcs, img_w: int, img_h: int) -> List[Dict]:
        try:
            x, y = wcs.all_world2pix(self._ra_deg, self._dec_deg, 0)
        except Exception as e:
            print(f"⚠️ WCS 投影失败: {e}")
            return []

        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        margin = 20
        valid = (
            np.isfinite(x) & np.isfinite(y)
            & (x >= -margin) & (x < img_w + margin)
            & (y >= -margin) & (y < img_h + margin)
        )
        out = []
        for idx in np.where(valid)[0]:
            c = self.catalog[idx]
            out.append({**c, "px": float(x[idx]), "py": float(y[idx])})
        return out