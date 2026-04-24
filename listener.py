# listener.py
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from logger import setup_logger

log = setup_logger("listener")

class QueueHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/queue":
            query = parse_qs(parsed.query, keep_blank_values=True)
            queues = query.get("queues[]", [])
            log.info(f"[REQUEST] queues={queues} from {self.client_address[0]}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK\n")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found\n")

    def log_message(self, format, *args):
        # Подавляем стандартный вывод http.server, всё идёт в наш логгер
        log.debug("%s", format % args)

def start_listener(host: str, port: int) -> threading.Thread:
    server = ThreadingHTTPServer((host, port), QueueHandler)
    log.info(f"HTTP listener started on {host}:{port}")
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t
