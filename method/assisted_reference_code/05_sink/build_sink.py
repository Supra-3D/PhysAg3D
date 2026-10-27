"""Current-image-specific sink refinement through the new skill."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from blender_common import Builder
from refine_sink import build
B=Builder(ROOT)
B.raw()
build(B)
B.export()
