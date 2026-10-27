from pathlib import Path
import sys
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from blender_common import Builder
B=Builder(R);B.raw()
