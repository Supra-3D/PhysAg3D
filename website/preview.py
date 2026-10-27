from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse, os, re, sys, threading, webbrowser
from urllib.parse import parse_qsl, urlencode, urlparse

# Keep generated Python caches outside the delivered website.
sys.dont_write_bytecode = True


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """Serve local video seeks without downloading or restarting the whole film."""

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        # Keep one live preview URL; cached HTML must not strand users on old UI.
        # The viewer API already supplies its own cache policy.
        if not any(line.lower().startswith(b"cache-control:") for line in self._headers_buffer):
            route = urlparse(self.path).path
            live_file = route.endswith("/") or Path(route).suffix in {".html", ".css", ".js", ".json"}
            self.send_header("Cache-Control", "no-store" if live_file else "no-cache, must-revalidate")
        super().end_headers()

    def send_head(self):
        self._byte_range = None
        requested_range = self.headers.get("Range")
        filename = self.translate_path(self.path)
        # Range only applies to GET. HEAD returns the normal full-file headers.
        # Keep the base handler's directory redirects and conditional requests.
        if self.command != "GET" or not requested_range or os.path.isdir(filename):
            return super().send_head()
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested_range.strip())
        if not match or not any(match.groups()):
            # Unsupported units, malformed ranges and multipart requests may be ignored.
            return super().send_head()
        try:
            source = open(filename, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        stat = os.fstat(source.fileno())
        size = stat.st_size
        modified = self.date_time_string(stat.st_mtime)
        if_range = self.headers.get("If-Range")
        if if_range and if_range != modified:
            source.close()
            return super().send_head()
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            suffix = int(last)
            start = max(0, size - suffix)
            end = size - 1
        if start >= size or start > end:
            source.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        source.seek(start)
        self._byte_range = (start, end)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(filename))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", modified)
        self.end_headers()
        return source

    def copyfile(self, source, outputfile):
        try:
            if self._byte_range is None:
                return super().copyfile(source, outputfile)
            start, end = self._byte_range
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                outputfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers cancel pending media requests while switching films or seeking.
            pass

def make_handler(root, data_dir=None):
    """Keep the existing media server and mount the original live viewer beside it."""
    candidates = [root / ".viewer-python"]
    for candidate in candidates:
        if candidate.is_dir():
            sys.path.insert(0, str(candidate))
            break
    try:
        from viewer.server import Application, Handler as ViewerHandler
    except ImportError as exc:
        raise RuntimeError(
            "Explore requires its Python dependencies. Run: "
            "python -m pip install -r viewer/requirements.txt"
        ) from exc

    class SiteRequestHandler(ViewerHandler, RangeRequestHandler):
        def redirect_page_entry(self):
            parsed = urlparse(self.path)
            if parsed.path not in ("/", "/index.html"):
                return False
            query = urlencode([(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "v"])
            destination = "/" + ("?" + query if query else "")
            if self.path == destination:
                return False
            self.send_response(302)
            self.send_header("Location", destination)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True

        def do_GET(self):
            if self.redirect_page_entry():
                return
            route = urlparse(self.path).path
            if route.startswith("/api/"):
                return self.dispatch()
            if route == "/viewer":
                self.send_response(308)
                self.send_header("Location", "/viewer/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if route.startswith("/viewer/"):
                original = self.path
                self.path = self.path[len("/viewer"):]
                try:
                    return self.dispatch()
                finally:
                    self.path = original
            return RangeRequestHandler.do_GET(self)

        def do_HEAD(self):
            if self.redirect_page_entry():
                return
            if urlparse(self.path).path.startswith("/viewer/"):
                original = self.path
                self.path = "/viewer/web/" + self.path[len("/viewer/"):]
                try:
                    return RangeRequestHandler.do_HEAD(self)
                finally:
                    self.path = original
            return RangeRequestHandler.do_HEAD(self)

    app = Application(data_dir or root / "viewer/.runtime")
    return partial(SiteRequestHandler, directory=str(root)), app


def main():
    parser = argparse.ArgumentParser(description="Preview the PhysAg3D website locally.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--viewer-data-dir", type=Path, default=None)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    handler, app = make_handler(root, args.viewer_data_dir)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        app.closed.set()
        raise SystemExit(f"Preview port {args.port} is unavailable. Stop the existing preview before restarting. {exc}")
    server.app = app
    server.daemon_threads = True
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    print("PhysAg3D preview: " + url, flush=True)
    print("Explore: local MuJoCo physics and bundled 3D assets. No remote connection required.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.closed.set()
        server.server_close()

if __name__ == "__main__":
    main()
