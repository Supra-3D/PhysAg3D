"""Local test mirror of the pinned binary assets; never included in Pages."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
PREFIX = '/PhysAg3D/'


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        route = unquote(urlsplit(self.path).path)
        if not route.startswith(PREFIX):
            self.send_error(404)
            return None
        relative = route[len(PREFIX):]
        if relative.startswith('__fixtures/'):
            relative = 'website/' + relative[len('__fixtures/'):]
        elif relative.split('/')[0] in {'.git', 'website', 'scripts'}:
            self.send_error(404)
            return None
        if not (ROOT / relative).resolve().is_relative_to(ROOT):
            self.send_error(404)
            return None
        self.path = '/' + relative
        return super().send_head()

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    print('Fixture preview: http://127.0.0.1:8876/PhysAg3D/', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8876), Handler).serve_forever()
