import argparse
import os
from pathlib import Path
import runpy
import socket
import sys

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ['PHYSAG_VIEWER_DEPS'] = str(ROOT / '.viewer-python')
parser = argparse.ArgumentParser(description='Start the bundled PhysAg3D website.')
parser.add_argument('--no-browser', action='store_true')
parser.add_argument('--port', type=int, default=8765)
args = parser.parse_args()
with socket.socket() as probe:
    try:
        probe.bind(('127.0.0.1', args.port))
        port = args.port
    except OSError:
        if args.port != 8765:
            raise SystemExit('Requested preview port is already in use.')
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
sys.argv = [str(ROOT/'preview.py'), '--port', str(port)]
if args.no_browser:
    sys.argv.append('--no-browser')
runpy.run_path(str(ROOT/'preview.py'), run_name='__main__')
