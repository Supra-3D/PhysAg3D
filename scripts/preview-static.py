"""Preview the Pages build at its real /PhysAg3D/ URL prefix."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "/PhysAg3D"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        path = urlsplit(self.path).path
        if path in ("/", PREFIX):
            self.send_response(302)
            self.send_header("Location", PREFIX + "/")
            self.end_headers()
            return None
        if not path.startswith(PREFIX + "/"):
            self.send_error(404)
            return None
        relative = path[len(PREFIX) + 1:]
        if relative.split("/")[0] in {".git", "website", "scripts", "README.md", "_config.yml"}:
            self.send_error(404)
            return None
        self.path = self.path[len(PREFIX):]
        return super().send_head()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8875)
    args = parser.parse_args()
    print(f"Static preview: http://127.0.0.1:{args.port}{PREFIX}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
