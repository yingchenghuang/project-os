"""Render the DXF to PNG/PDF for checking (swaps the CJK font for one available on Linux)."""
import sys

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

src, out = sys.argv[1], sys.argv[2:]
bbox = None
if "--crop" in out:
    i = out.index("--crop")
    bbox = tuple(map(float, out[i + 1:i + 5]))
    out = out[:i]
doc = ezdxf.readfile(src)
doc.styles.get("TW").dxf.font = "wqy-zenhei.ttc"
fig = plt.figure(figsize=(42 / 2.54 * 1.0, 29.7 / 2.54 * 1.0))
ax = fig.add_axes([0, 0, 1, 1])
ctx = RenderContext(doc)
cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                    lineweight_scaling=1.2, min_lineweight=0.12)
Frontend(ctx, MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace(), finalize=True)
if bbox:
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
for o in out:
    fig.savefig(o, dpi=int(sys.argv[-1]) if o.endswith(".png") and sys.argv[-1].isdigit() else 200)
