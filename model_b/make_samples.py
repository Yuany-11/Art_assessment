"""生成基线服务自测用的样例图（测试夹具，不是证据材料）。

用法：python make_samples.py
输出到 ./samples/
"""
import os

import numpy as np
from PIL import Image, ImageFilter

OUT = os.path.join(os.path.dirname(__file__), "samples")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(42)


def colorful(size=640):
    yy, xx = np.mgrid[0:size, 0:size]
    base = np.stack([
        128 + 100 * np.sin(xx / 55.0),
        128 + 100 * np.sin(yy / 70.0 + 1.2),
        128 + 100 * np.sin((xx + yy) / 90.0 + 2.4),
    ], axis=2)
    for _ in range(12):
        cy, cx = rng.integers(80, size - 80, 2)
        r = int(rng.integers(30, 110))
        color = rng.integers(0, 256, 3)
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 < r ** 2
        base[mask] = 0.35 * base[mask] + 0.65 * color
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def main():
    color = colorful()
    color.save(os.path.join(OUT, "demo_color.png"))

    gray = color.convert("L").filter(ImageFilter.FIND_EDGES).convert("RGB")
    gray.save(os.path.join(OUT, "demo_sketch.png"))

    color.filter(ImageFilter.GaussianBlur(radius=8)).save(os.path.join(OUT, "demo_blur.png"))

    Image.new("RGB", (640, 640), (255, 255, 255)).save(os.path.join(OUT, "demo_blank.png"))
    Image.new("RGB", (640, 640), (0, 0, 0)).save(os.path.join(OUT, "demo_dark.png"))

    print("samples written to", OUT)


if __name__ == "__main__":
    main()
