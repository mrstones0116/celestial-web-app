from typing import List, Optional, Dict, Any
from .schemas import TourStep, TourTarget, CameraTarget, Narration


def _step(
    *,
    index: int,
    title: str,
    targets: List[TourTarget],
    ra: float,
    dec: float,
    fov: float,
    short: str,
    long: str,
    tip: Optional[str] = None,
    hint: Optional[str] = None,
    minutes: int = 3,
) -> TourStep:
    return TourStep(
        step_index=index,
        title=title,
        targets=targets,
        camera=CameraTarget(
            center_ra_deg=ra,
            center_dec_deg=dec,
            fov_deg=fov,
            highlight_ids=[t.id for t in targets],
        ),
        narration=Narration(short=short, long=long, observation_tip=tip),
        estimated_minutes=minutes,
        next_hint=hint,
    )


# ---------- 夏季星空 ----------

def build_summer_sky_steps(max_steps: int = 10) -> List[TourStep]:
    vega = TourTarget(
        type="star", id="Vega", hyg_id="HIP 91262",
        name_zh="织女星", name_en="Vega",
        constellation="Lyr", ra_deg=279.234, dec_deg=38.784, magnitude=0.03,
    )
    altair = TourTarget(
        type="star", id="Altair", hyg_id="HIP 97649",
        name_zh="牛郎星", name_en="Altair",
        constellation="Aql", ra_deg=297.696, dec_deg=8.868, magnitude=0.77,
    )
    deneb = TourTarget(
        type="star", id="Deneb", hyg_id="HIP 102098",
        name_zh="天津四", name_en="Deneb",
        constellation="Cyg", ra_deg=310.358, dec_deg=45.280, magnitude=1.25,
    )

    steps = [
        _step(
            index=0, title="织女星", targets=[vega],
            ra=279.234, dec=38.784, fov=25,
            short="夏季大三角中最亮的一颗。",
            long="织女星是北半球夏季夜空的重要标志星，视星等约0.03，呈蓝白色。它位于天琴座，是夏季观星的第一站。",
            tip="先找到东北方高空的亮星，它通常比周围恒星更亮。",
            hint="找到织女星后，我们向东南方向寻找牛郎星。",
        ),
        _step(
            index=1, title="牛郎星", targets=[altair],
            ra=297.696, dec=8.868, fov=25,
            short="与织女星隔银河相望。",
            long="牛郎星位于天鹰座，两侧各有一颗较暗的星，民间称为河鼓一和河鼓三，象征牛郎的一双儿女。",
            tip="观察牛郎星两侧的暗星，可以更容易辨认天鹰座。",
            hint="接下来我们找夏季大三角的第三颗星：天津四。",
        ),
        _step(
            index=2, title="天津四", targets=[deneb],
            ra=310.358, dec=45.280, fov=25,
            short="天鹅座的尾羽。",
            long="天津四位于天鹅座，是夏季大三角的第三颗星。它所在的天鹅座像一只沿银河飞翔的天鹅。",
            tip="天津四附近恒星密集，适合观察银河。",
            hint="现在你已经找到了夏季大三角。",
        ),
    ]
    return steps[:max_steps]


# ---------- 冬季星空 ----------

def build_winter_sky_steps(max_steps: int = 10) -> List[TourStep]:
    betelgeuse = TourTarget(
        type="star", id="Betelgeuse", hyg_id="HIP 27989",
        name_zh="参宿四", name_en="Betelgeuse",
        constellation="Ori", ra_deg=88.793, dec_deg=7.407, magnitude=0.42,
    )
    rigel = TourTarget(
        type="star", id="Rigel", hyg_id="HIP 24436",
        name_zh="参宿七", name_en="Rigel",
        constellation="Ori", ra_deg=78.634, dec_deg=-8.202, magnitude=0.13,
    )
    sirius = TourTarget(
        type="star", id="Sirius", hyg_id="HIP 32349",
        name_zh="天狼星", name_en="Sirius",
        constellation="CMa", ra_deg=101.287, dec_deg=-16.716, magnitude=-1.46,
    )

    steps = [
        _step(
            index=0, title="猎户座", targets=[betelgeuse, rigel],
            ra=84.0, dec=0.0, fov=35,
            short="冬季星空最醒目的星座。",
            long="猎户座是冬季夜空最容易辨认的星座之一，中央三颗星组成猎户腰带。",
            tip="先找到三颗排成一线的亮星，它们就是猎户腰带。",
            hint="接下来我们看猎户座的两颗主星。",
        ),
        _step(
            index=1, title="参宿四", targets=[betelgeuse],
            ra=88.793, dec=7.407, fov=20,
            short="红色超巨星。",
            long="参宿四是猎户座的肩膀，呈橙红色，是一颗红超巨星。",
            tip="注意它的颜色与周围蓝白色恒星不同。",
            hint="接下来看猎户座另一颗亮星：参宿七。",
        ),
        _step(
            index=2, title="参宿七", targets=[rigel],
            ra=78.634, dec=-8.202, fov=20,
            short="蓝白色亮星。",
            long="参宿七位于猎户座的脚部，是蓝白色超巨星，亮度略高于参宿四。",
            tip="参宿七通常比参宿四更稳定明亮。",
            hint="最后我们沿着猎户腰带向南找到天狼星。",
        ),
        _step(
            index=3, title="天狼星", targets=[sirius],
            ra=101.287, dec=-16.716, fov=25,
            short="全天最亮恒星。",
            long="天狼星是夜空中最亮的恒星，位于大犬座。冬季观星时非常容易找到。",
            tip="如果它靠近地平线，可能会闪烁出彩色光芒。",
            hint="冬季星空漫游完成。",
        ),
    ]
    return steps[:max_steps]


# ---------- 亮星之旅 ----------

def build_bright_star_steps(max_steps: int = 10) -> List[TourStep]:
    sirius = TourTarget(
        type="star", id="Sirius", hyg_id="HIP 32349",
        name_zh="天狼星", name_en="Sirius",
        constellation="CMa", ra_deg=101.287, dec_deg=-16.716, magnitude=-1.46,
    )
    arcturus = TourTarget(
        type="star", id="Arcturus", hyg_id="HIP 69673",
        name_zh="大角星", name_en="Arcturus",
        constellation="Boo", ra_deg=213.915, dec_deg=19.182, magnitude=-0.05,
    )
    steps = [
        _step(
            index=0, title="天狼星", targets=[sirius],
            ra=101.287, dec=-16.716, fov=30,
            short="全天最亮恒星。",
            long="天狼星是夜空中最亮的恒星，位于大犬座。",
            tip="冬季夜晚最容易找到。",
            hint="接下来看大角星。",
        ),
        _step(
            index=1, title="大角星", targets=[arcturus],
            ra=213.915, dec=19.182, fov=30,
            short="北天最亮恒星之一。",
            long="大角星是牧夫座的主星，呈橙黄色。",
            tip="春季观星的重要标志。",
            hint="亮星漫游完成。",
        ),
    ]
    return steps[:max_steps]


# ---------- 梅西耶马拉松 ----------

def build_messier_marathon_steps(max_steps: int = 10) -> List[TourStep]:
    m42 = TourTarget(
        type="messier", id="M42", hyg_id=None,
        name_zh="猎户座大星云", name_en="Orion Nebula",
        constellation="Ori", ra_deg=83.822, dec_deg=-5.391, magnitude=4.0,
    )
    m45 = TourTarget(
        type="messier", id="M45", hyg_id=None,
        name_zh="昴星团", name_en="Pleiades",
        constellation="Tau", ra_deg=56.75, dec_deg=24.117, magnitude=1.6,
    )
    steps = [
        _step(
            index=0, title="M42 猎户座大星云", targets=[m42],
            ra=83.822, dec=-5.391, fov=20,
            short="最容易观测的深空天体之一。",
            long="M42位于猎户座佩剑位置，肉眼可见模糊光斑，双筒望远镜下更明显。",
            tip="从猎户腰带向下寻找佩剑。",
            hint="接下来看昴星团。",
        ),
        _step(
            index=1, title="M45 昴星团", targets=[m45],
            ra=56.75, dec=24.117, fov=25,
            short="著名的疏散星团。",
            long="M45是金牛座中的疏散星团，肉眼可见多颗蓝色恒星聚集。",
            tip="在无月暗夜观测效果最佳。",
            hint="梅西耶马拉松示例完成。",
        ),
    ]
    return steps[:max_steps]