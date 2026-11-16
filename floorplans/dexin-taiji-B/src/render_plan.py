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
dpi = 200
if out and out[-1].isdigit():
    dpi = int(out.pop())
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
SHEETS = [(-3500, -9300, 38500, 20400), (-3500, -40500, 38500, -10800)]   # A3 frames: plan, sections
if "--sheets" in out:                       # one page / image per A3 frame
    out.remove("--sheets")
    from matplotlib.backends.backend_pdf import PdfPages
    fig.set_size_inches(42 / 2.54, 29.7 / 2.54)
    ax.set_position([0, 0, 1, 1])
    ax.set_aspect("equal", adjustable="box")
    for o in out:
        if o.endswith(".pdf"):
            with PdfPages(o) as pdf:
                for b in SHEETS:
                    ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3]); pdf.savefig(fig)
        else:
            for i, b in enumerate(SHEETS):
                ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3])
                fig.savefig(o.replace(".png", f"_{i + 1}.png"), dpi=dpi)
    sys.exit()
if bbox:
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
for o in out:
    fig.savefig(o, dpi=dpi)
