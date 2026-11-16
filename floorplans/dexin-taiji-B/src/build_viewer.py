"""Embed the GLB into the viewer template -> standalone HTML."""
import base64, sys
from pathlib import Path
tpl = Path(__file__).with_name("viewer_template.html").read_text(encoding="utf-8")
glb = base64.b64encode(Path(sys.argv[1]).read_bytes()).decode()
three = sys.argv[3] if len(sys.argv) > 3 else "https://cdn.jsdelivr.net/npm/three@0.160.0"
Path(sys.argv[2]).write_text(tpl.replace("%%GLB%%", glb).replace("%%THREE%%", three), encoding="utf-8")
