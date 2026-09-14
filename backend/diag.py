import sys
sys.path.insert(0, ".")

from data_loader import HYGDataLoader

l = HYGDataLoader()
r = l.load_data()
print("load_data:", r)

stars = l.get_bright_stars(max_mag=6.0)
print(f"get_bright_stars(6.0): {len(stars)} 颗")
if stars:
    print("首颗字段名:", list(stars[0].keys()))
    print("首颗内容:", stars[0])