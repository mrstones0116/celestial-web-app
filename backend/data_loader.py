"""
HYG星表数据加载与处理模块
"""
import pandas as pd
import numpy as np
import requests
from io import StringIO
from typing import Optional, Dict, Any


class HYGDataLoader:
    """HYG星表数据加载器"""

    HYG_URL = "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v41.csv"
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
        """从GitHub下载并处理HYG星表数据"""
        try:
            response = requests.get(self.HYG_URL, timeout=60)
            response.raise_for_status()
            self.df = pd.read_csv(StringIO(response.text))

            total_raw = len(self.df)

            # 筛选：有光谱类型，星等 < 6（肉眼可见）
            mask = (
                (self.df['mag'].notna()) &
                (self.df['mag'] < 6) &
                (self.df['spect'].notna())
            )
            self.df = self.df[mask].copy()

            # 确保必要列
            required_columns = ['ra', 'dec', 'mag', 'proper', 'spect', 'dist', 'absmag']
            for col in required_columns:
                if col not in self.df.columns:
                    if col == 'proper':
                        self.df[col] = [f"Star_{i}" for i in range(len(self.df))]
                    else:
                        self.df[col] = 0

            # 星星名称
            self.df['name'] = self.df['proper'].fillna(self.df['bf'].fillna("未知"))

            # 星座
            if 'con' in self.df.columns:
                self.df['constellation'] = self.df['con'].fillna("未知")
            else:
                self.df['constellation'] = "未知"

            # 光谱类型
            self.df['spect'] = self.df['spect'].fillna("G2V").astype(str).str.strip()

            # 坐标转换
            self.df['ra_hours'] = self.df['ra']
            self.df['ra_deg'] = self.df['ra'] * 15
            self.df['ra_rad'] = np.deg2rad(self.df['ra_deg'])
            self.df['dec_rad'] = np.deg2rad(self.df['dec'])

            # 球面 → 笛卡尔
            self.df['x'] = np.cos(self.df['dec_rad']) * np.cos(self.df['ra_rad'])
            self.df['y'] = np.cos(self.df['dec_rad']) * np.sin(self.df['ra_rad'])
            self.df['z'] = np.sin(self.df['dec_rad'])

            # 距离转换
            self.df['dist_parsec'] = pd.to_numeric(self.df['dist'], errors='coerce').fillna(100)
            self.df.loc[self.df['dist_parsec'] <= 0, 'dist_parsec'] = 100
            self.df['dist_ly'] = self.df['dist_parsec'] * self.PARSEC_TO_LY

            # 光谱分类
            self.df['spect_class'] = self.df['spect'].apply(self._get_spectral_class)

            self.loaded = True

            return {
                'success': True,
                'message': f'成功加载 {len(self.df)} 颗星（原始 {total_raw} 条记录）',
                'total_stars': len(self.df),
                'raw_records': total_raw
            }

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
        """获取亮星标注数据"""
        if not self.loaded or self.df is None:
            return []

        bright = self.df[self.df['mag'] <= max_mag].copy()
        result = []
        for _, row in bright.iterrows():
            name = row['name'] if row['name'] != '未知' else f"Star_{row.name}"
            result.append({
                'name': name,
                'x': float(row['x']),
                'y': float(row['y']),
                'z': float(row['z']),
                'mag': float(row['mag']),
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