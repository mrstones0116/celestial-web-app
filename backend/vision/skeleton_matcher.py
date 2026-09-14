"""
星座识别器（距离矩阵匹配版）
流程：
1. 取照片中最亮的 10 颗星
2. 计算成对像素距离矩阵（归一化）
3. 与 88 星座模板的角距离矩阵逐一比较
4. 只返回 1 个最佳匹配星座 + 全部恒星
"""
import os
import json
import numpy as np
from itertools import combinations
from typing import List, Dict, Optional

CONST_FULL_NAMES = {
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


class SkeletonMatcher:

    def __init__(self, lines_json_path=None, hyg_stars=None, max_match_dist_deg=3.0):
        if lines_json_path is None:
            lines_json_path = self._locate_data_file()
        self.hyg_stars = hyg_stars or []
        self.max_match_dist = max_match_dist_deg
        self._build_hyg_index()
        self.constellations: Dict[str, Dict] = {}
        if lines_json_path and os.path.exists(lines_json_path):
            self.constellations = self._load_constellations(lines_json_path)
            print(f"✅ 已加载 {len(self.constellations)} 个星座模板")
        else:
            print("⚠️ 星座数据文件未找到")

    # ================================================================
    def _locate_data_file(self):
        base = os.path.dirname(os.path.abspath(__file__))
        for p in [
            os.path.join(base, "..", "..", "frontend", "data", "constellations.lines.json"),
            os.path.join(base, "..", "frontend", "data", "constellations.lines.json"),
            os.path.join(os.getcwd(), "frontend", "data", "constellations.lines.json"),
        ]:
            p = os.path.normpath(p)
            if os.path.exists(p):
                return p
        return None

    # ================================================================
    def _build_hyg_index(self):
        vecs, stars = [], []
        for s in self.hyg_stars:
            ra = s.get("ra_hours", 0) * 15.0 * np.pi / 180.0
            dec = s.get("dec", 0) * np.pi / 180.0
            vecs.append([np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)])
            stars.append(s)
        self._hyg_vecs = np.array(vecs, dtype=np.float64) if vecs else None
        self._hyg_list = stars

    def _find_nearest_star(self, ra_deg, dec_deg):
        if self._hyg_vecs is None or len(self._hyg_list) == 0:
            return None
        ra = ra_deg * np.pi / 180.0
        dec = dec_deg * np.pi / 180.0
        vec = np.array([np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)])
        dots = np.clip(self._hyg_vecs @ vec, -1, 1)
        angles = np.degrees(np.arccos(dots))
        idx = int(np.argmin(angles))
        return self._hyg_list[idx] if angles[idx] <= self.max_match_dist else None

    @staticmethod
    def _ang_dist_deg(ra1, dec1, ra2, dec2):
        ra1, dec1, ra2, dec2 = map(np.radians, [ra1, dec1, ra2, dec2])
        cosd = (np.sin(dec1)*np.sin(dec2) + np.cos(dec1)*np.cos(dec2)*np.cos(ra1-ra2))
        return float(np.degrees(np.arccos(np.clip(cosd, -1, 1))))

    # ================================================================
    #  加载 88 星座
    # ================================================================
    def _load_constellations(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            geojson = json.load(f)
        constellations = {}
        for feature in geojson.get('features', []):
            const_id = feature.get('id', 'Unknown')
            coords = feature.get('geometry', {}).get('coordinates', [])
            if not coords:
                continue
            endpoint_map = {}
            edges_set = set()
            for line in coords:
                for i in range(len(line) - 1):
                    p1 = (round(line[i][0], 4), round(line[i][1], 4))
                    p2 = (round(line[i+1][0], 4), round(line[i+1][1], 4))
                    if p1 not in endpoint_map:
                        endpoint_map[p1] = len(endpoint_map)
                    if p2 not in endpoint_map:
                        endpoint_map[p2] = len(endpoint_map)
                    i1, i2 = endpoint_map[p1], endpoint_map[p2]
                    if i1 != i2:
                        edges_set.add(tuple(sorted([i1, i2])))
            if len(endpoint_map) < 3:
                continue
            stars = []
            for (ra, dec), idx in sorted(endpoint_map.items(), key=lambda x: x[1]):
                hyg = self._find_nearest_star(ra, dec)
                name = (hyg.get('name') or '').strip() if hyg else ''
                mag = float(hyg['mag']) if hyg and hyg.get('mag') is not None else 99.0
                if not name:
                    name = f"{const_id}_{idx}"
                stars.append({'ra': ra, 'dec': dec, 'name': name, 'mag': mag})
            constellations[const_id] = {
                'stars': stars,
                'edges': [list(e) for e in edges_set],
            }
        return constellations

    # ================================================================
    #  ★ 核心：距离矩阵匹配（只返回 1 个星座）
    # ================================================================
    def match(self, detected_stars, img_w, img_h, top_n=10):
        top = sorted(detected_stars, key=lambda s: s['flux'], reverse=True)[:top_n]
        n = len(top)
        if n < 3:
            return None

        # 归一化像素距离矩阵
        photo_pos = np.array([[s['x'], s['y']] for s in top])
        photo_dist = np.zeros((n, n))
        for i in range(n):
            for j in range(i+1, n):
                d = np.hypot(photo_pos[i,0]-photo_pos[j,0], photo_pos[i,1]-photo_pos[j,1])
                photo_dist[i,j] = d; photo_dist[j,i] = d
        pm = photo_dist.max()
        if pm < 1:
            return None
        photo_norm = photo_dist / pm

        best_name = None
        best_err = 0.30          # 容差
        best_assignment = None
        best_data = None

        for name, cdata in self.constellations.items():
            k = len(cdata['stars'])
            if k < 3 or k > n:
                continue
            cs = cdata['stars']

            # 归一化角距离矩阵
            const_dist = np.zeros((k, k))
            for i in range(k):
                for j in range(i+1, k):
                    d = self._ang_dist_deg(cs[i]['ra'], cs[i]['dec'], cs[j]['ra'], cs[j]['dec'])
                    const_dist[i,j] = d; const_dist[j,i] = d
            cm = const_dist.max()
            if cm < 1e-6:
                continue
            const_norm = const_dist / cm

            # 星座星按亮度排序（最亮在前）
            mag_order = sorted(range(k), key=lambda i: cs[i].get('mag', 99))

            # 限制组合数
            combos = list(combinations(range(n), k))
            if len(combos) > 120:
                combos = [tuple(range(k))]

            for combo in combos:
                assignment = {combo[i]: mag_order[i] for i in range(k)}
                err = self._assign_err(photo_norm, const_norm, assignment)

                # 交换优化（3 轮）
                for _ in range(3):
                    improved = False
                    for i in range(k):
                        for j in range(i+1, k):
                            pi, pj = combo[i], combo[j]
                            assignment[pi], assignment[pj] = assignment[pj], assignment[pi]
                            ne = self._assign_err(photo_norm, const_norm, assignment)
                            if ne < err:
                                err = ne; improved = True
                            else:
                                assignment[pi], assignment[pj] = assignment[pj], assignment[pi]
                    if not improved:
                        break

                if err < best_err:
                    best_err = err
                    best_name = name
                    best_assignment = assignment.copy()
                    best_data = cdata

        if best_name is None:
            return None

        return {
            'constellation': best_name,
            'assignment': best_assignment,
            'data': best_data,
            'error': best_err,
            'confidence': max(0.3, 1.0 - best_err / 0.30),
        }

    def _assign_err(self, photo_norm, const_norm, assignment):
        total, cnt = 0.0, 0
        idx = list(assignment.keys())
        for i in range(len(idx)):
            for j in range(i+1, len(idx)):
                pi, pj = idx[i], idx[j]
                ci, cj = assignment[pi], assignment[pj]
                total += abs(photo_norm[pi,pj] - const_norm[ci,cj])
                cnt += 1
        return total / max(cnt, 1)

    # ================================================================
    #  输出
    # ================================================================
    def get_skeleton_pixels(self, result, detected_stars):
        if not result:
            return []
        a = result['assignment']
        lines = []
        for edge in result['data']['edges']:
            pi = pj = None
            for pk, ck in a.items():
                if ck == edge[0]: pi = pk
                if ck == edge[1]: pj = pk
            if pi is not None and pj is not None and pi < len(detected_stars) and pj < len(detected_stars):
                lines.append([
                    [detected_stars[pi]['x'], detected_stars[pi]['y']],
                    [detected_stars[pj]['x'], detected_stars[pj]['y']],
                ])
        return lines

    def get_full_name(self, abbrev):
        return CONST_FULL_NAMES.get(abbrev, abbrev)