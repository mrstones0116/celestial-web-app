"""
星点检测模块 —— OpenCV 从夜空照片中提取亮点
"""
import cv2
import numpy as np
from typing import List, Dict


def detect_stars(
    image_path: str,
    max_stars: int = 60,
    min_area: int = 3,
    blur_ksize: int = 5,
) -> List[Dict]:
    """
    检测夜空照片中的星点

    Returns:
        按亮度降序排列的星点列表
        [{ x, y, brightness, area, radius }, ...]
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ---- 去噪 ----
    blurred = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)

    # ---- Otsu 自适应阈值（对明暗不均的夜空照片效果好） ----
    _, thresh = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # ---- 形态学开运算：去掉孤立噪点 ----
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # ---- 连通区域检测 ----
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    stars: List[Dict] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # 区域平均亮度
        mask = np.zeros_like(gray)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        brightness = float(cv2.mean(gray, mask=mask)[0])

        stars.append({
            "x": cx,
            "y": cy,
            "brightness": brightness,
            "area": float(area),
            "radius": float(np.sqrt(area / np.pi)),
        })

    stars.sort(key=lambda s: s["brightness"], reverse=True)
    return stars[:max_stars]