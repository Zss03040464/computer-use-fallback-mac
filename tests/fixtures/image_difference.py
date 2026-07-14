from __future__ import annotations

import json
import sys

from PIL import Image, ImageChops, ImageStat


first = Image.open(sys.argv[1]).convert("RGB")
second = Image.open(sys.argv[2]).convert("RGB")
if first.size != second.size:
    raise SystemExit(f"image sizes differ: {first.size} != {second.size}")
difference = ImageChops.difference(first, second)
means = ImageStat.Stat(difference).mean
ratio = sum(means) / (len(means) * 255.0)
print(json.dumps({"difference": ratio, "size": list(first.size)}))
