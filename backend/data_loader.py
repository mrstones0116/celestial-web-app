"""
HYG星表数据加载与处理模块
"""
from pathlib import Path
from typing import Optional, Dict, Any
from io import StringIO

import pandas as pd
import numpy as np
import requests


class HYGDataLoader:
    """HYG星表数据加载器"""

    HYG_URL = "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v41.csv"
    LOCAL_CSV = Path(__file__).resolve().parent / "data" / "hygdata_v41.csv"
    PARSEC_TO_LY = 3.26156

    SPECTRAL_COLORS = {
        'O': '#9bb0ff',
        'B': '#aabfff',
        'A': '#cad7ff',
        'F': '#f8f7ff',
        'G': '#fff4ea',
        'K': '#ffd2a1',
        'M': '#ffcc6f',
        'Other': '#aaaaaa'
    }

    SPECTRAL_INFO = {
        'O': {'name': 'O型星', 'color_name': '蓝色', 'temp': '最热(>30,000K)', 'color': '#9bb0ff'},
        'B': {'name': 'B型星', 'color_name': '蓝白色', 'temp': '很热(10,000-30,000K)', 'color': '#aabfff'},
        'A': {'name': 'A型星', 'color_name': '白色', 'temp': '热(7,500-10,000K)', 'color': '#cad7ff'},
        'F': {'name': 'F型星', 'color_name': '黄白色', 'temp': '中等(6,000-7,500K)', 'color': '#f8f7ff'},
        'G': {'name': 'G型星', 'color_name': '黄色', 'temp': '中等(5,200-6,000K)', 'color': '#fff4ea'},
        'K': {'name': 'K型星', 'color_name': '橙色', 'temp': '较冷(3,700-5,200K)', 'color': '#ffd2a1'},
        'M': {'name': 'M型星', 'color_name': '红色', 'temp': '最冷(<3,700K)', 'color': '#ffcc6f'},
    }

    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.loaded: bool = False

    def load_data(self) -> Dict[str, Any]:
        """优先读本地 CSV；没有本地文件才从 GitHub 下载。"""
        try:
            # ---- 1) 本地优先 ----
            if self.LOCAL_CSV.exists():
                print(f"📂 读取本地星表: {self.LOCAL_CSV}")
                self.df = pd.read_csv(self.LOCAL_CSV, low_memory=False)
                total_raw = len(self.df)
            else:
                # ---- 2) 本地没有，尝试下载并缓存 ----
                print(f"⬇️  本地无星表，尝试下载: {self.HYG_URL}")
                response = requests.get(self.HYG_URL, timeout=120, stream=True)
                response.raise_for_status()

                self.LOCAL_CSV.parent.mkdir(parents=True, exist_ok=True)
                with open(self.LOCAL_CSV, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)

                print(f"✅ 已缓存到: {self.LOCAL_CSV}")
                self.df = pd.read_csv(self.LOCAL_CSV, low_memory=False)
                total_raw = len(self.df)

            # ---- 3) 清洗 ----
            mask = (
                (self.df['mag'].notna()) &
                (self.df['mag'] < 6) &
                (self.df['spect'].notna())
            )
            self.df = self.df[mask].copy()

            required_columns = ['ra', 'dec', 'mag', 'proper', 'spect', 'dist', 'absmag']
            for col in required_columns:
                if col not in self.df.columns:
                    if col == 'proper':
                        self.df[col] = [f"Star_{i}" for i in range(len(self.df))]
                    else:
                        self.df[col] = 0

            self.df['name'] = self.df['proper'].fillna(self.df['bf'].fillna("未知"))

            if 'con' in self.df.columns:
                self.df['constellation'] = self.df['con'].fillna("未知")
            else:
                self.df['constellation'] = "未知"

            self.df['spect'] = self.df['spect'].fillna("G2V").astype(str).str.strip()

            self.df['ra_hours'] = self.df['ra']
            self.df['ra_deg'] = self.df['ra'] * 15
            self.df['ra_rad'] = np.deg2rad(self.df['ra_deg'])
            self.df['dec_rad'] = np.deg2rad(self.df['dec'])

            self.df['x'] = np.cos(self.df['dec_rad']) * np.cos(self.df['ra_rad'])
            self.df['y'] = np.cos(self.df['dec_rad']) * np.sin(self.df['ra_rad'])
            self.df['z'] = np.sin(self.df['dec_rad'])

            self.df['dist_parsec'] = pd.to_numeric(self.df['dist'], errors='coerce').fillna(100)
            self.df.loc[self.df['dist_parsec'] <= 0, 'dist_parsec'] = 100
            self.df['dist_ly'] = self.df['dist_parsec'] * self.PARSEC_TO_LY

            self.df['spect_class'] = self.df['spect'].apply(self._get_spectral_class)

            self.loaded = True

            return {
                'success': True,
                'message': f'成功加载 {len(self.df)} 颗星（原始 {total_raw} 条记录）',
                'total_stars': len(self.df),
                'raw_records': total_raw
            }

        except requests.exceptions.Timeout:
            return {'success': False, 'message': '下载超时。请手动下载 hygdata_v41.csv 放到 backend/data/'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'message': '无法连接 GitHub。请手动下载 hygdata_v41.csv 放到 backend/data/'}
        except Exception as e:
            return {'success': False, 'message': f'加载失败: {str(e)}'}

    def _get_spectral_class(self, spect_str: str) -> str:
        if pd.isna(spect_str) or not spect_str:
            return 'Other'
        spect_str = str(spect_str).strip().upper()
        if spect_str and spect_str[0] in self.SPECTRAL_COLORS:
            return spect_str[0]
        return 'Other'

    def get_stars(self, max_mag: float = 6.0) -> list:
        """获取筛选后的星星数据"""
        if not self.loaded or self.df is None:
            return []

        filtered = self.df[self.df['mag'] <= max_mag].copy()

        stars = []
        for _, row in filtered.iterrows():
            stars.append({
                'name': row['name'],
                'constellation': row['constellation'],
                'ra_hours': round(float(row['ra_hours']), 4),
                'dec': round(float(row['dec']), 4),
                'mag': round(float(row['mag']), 2),
                'absmag': round(float(row['absmag']), 2) if pd.notna(row['absmag']) else None,
                'spect': row['spect'],
                'spect_class': row['spect_class'],
                'dist_ly': round(float(row['dist_ly']), 1),
                'dist_pc': round(float(row['dist_parsec']), 1),
                'x': round(float(row['x']), 6),
                'y': round(float(row['y']), 6),
                'z': round(float(row['z']), 6),
            })
        return stars

    def get_bright_stars(self, max_mag: float = 2.5) -> list:
        """获取亮星数据（含 RA/Dec/星座，识别器需要完整字段）"""
        if not self.loaded or self.df is None:
            return []

        bright = self.df[
            (self.df['mag'] <= max_mag) &
            (self.df['constellation'] != '未知') &
            (self.df['name'] != 'Sol')
        ].copy()
        result = []
        for _, row in bright.iterrows():
            name = row['name'] if row['name'] != '未知' else f"Star_{row.name}"
            result.append({
                'name': name,
                'constellation': row['constellation'],
                'ra_hours': float(row['ra_hours']),
                'dec': float(row['dec']),
                'mag': float(row['mag']),
                'absmag': float(row['absmag']) if pd.notna(row['absmag']) else None,
                'spect': row['spect'],
                'spect_class': row['spect_class'],
                'dist_ly': float(row['dist_ly']),
                'x': float(row['x']),
                'y': float(row['y']),
                'z': float(row['z']),
            })
        return result

    def get_stats(self, max_mag: float = 6.0) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.loaded or self.df is None:
            return {}

        filtered = self.df[self.df['mag'] <= max_mag]

        spectral_dist = filtered['spect_class'].value_counts().to_dict()

        return {
            'total_stars': len(self.df),
            'current_count': len(filtered),
            'avg_mag': round(float(filtered['mag'].mean()), 2),
            'min_mag': round(float(filtered['mag'].min()), 2),
            'max_mag': round(float(filtered['mag'].max()), 2),
            'avg_absmag': round(float(filtered['absmag'].mean()), 2) if 'absmag' in filtered.columns else None,
            'avg_dist_ly': round(float(filtered['dist_ly'].mean()), 1),
            'max_dist_ly': round(float(filtered['dist_ly'].max()), 1),
            'constellation_count': int(filtered['constellation'].nunique()),
            'ra_range': [round(float(filtered['ra_hours'].min()), 2), round(float(filtered['ra_hours'].max()), 2)],
            'dec_range': [round(float(filtered['dec'].min()), 1), round(float(filtered['dec'].max()), 1)],
            'spectral_distribution': spectral_dist,
        }

    def get_constellation_stats(self, max_mag: float = 6.0) -> list:
        """获取星座统计"""
        if not self.loaded or self.df is None:
            return []

        filtered = self.df[self.df['mag'] <= max_mag]

        stats = filtered.groupby('constellation').agg(
            star_count=('name', 'count'),
            brightest_mag=('mag', 'min'),
            dimmest_mag=('mag', 'max'),
            avg_mag=('mag', 'mean')
        ).round(2).reset_index()

        stats = stats.sort_values('star_count', ascending=False)

        return stats.to_dict('records')

    def get_top_bright_stars(self, limit: int = 15, max_mag: float = 6.0) -> list:
        """获取最亮的星星列表"""
        if not self.loaded or self.df is None:
            return []

        filtered = self.df[self.df['mag'] <= max_mag]
        bright = filtered.nsmallest(limit, 'mag')

        result = []
        for _, row in bright.iterrows():
            result.append({
                'name': row['name'],
                'constellation': row['constellation'],
                'ra_hours': round(float(row['ra_hours']), 3),
                'dec': round(float(row['dec']), 2),
                'mag': round(float(row['mag']), 2),
                'absmag': round(float(row['absmag']), 2) if pd.notna(row['absmag']) else None,
                'spect': row['spect'],
                'dist_ly': round(float(row['dist_ly']), 1),
                'dist_pc': round(float(row['dist_parsec']), 1),
            })
        return result