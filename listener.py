# listener.py
import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from logger import setup_logger

log = setup_logger("listener")
ami_client = None
db_client = None

def set_clients(ami, db):
    global ami_client, db_client
    ami_client = ami
    db_client = db

# Маппинг статуса телефона из AMI в DB-формат
PHONE_MAP = {
    "not_in_use": "phoneready",
    "ringing": "phoneringing",
    "used": "phonebusy"
}

class QueueHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/queue":
            return self._respond(404, {"error": "Not Found"})

        queues = parse_qs(parsed.query, keep_blank_values=True).get("queues[]", [])
        if not queues:
            return self._respond(400, {"error": "Missing 'queues[]' parameter"})

        if not ami_client or not ami_client.authenticated:
            return self._respond(503, {"error": "AMI not connected"})
        if not db_client:
            return self._respond(503, {"error": "DB not connected"})

        log.info(f"[REQUEST] queues={queues} from {self.client_address[0]}")

        # 1. Собираем уникальных агентов из AMI
        seen_ids, ami_agents = set(), {}
        for q in queues:
            for agent in ami_client.queue_show(q):
                if agent["id"] not in seen_ids:
                    seen_ids.add(agent["id"])
                    ami_agents[agent["id"]] = agent

        # 2. Забираем данные из БД одним запросом
        db_records = db_client.get_agents_by_ids(list(seen_ids))

        # 3. Формируем итоговый массив
        result = {}
        for aid, ami_data in ami_agents.items():
            db = db_records.get(aid, {})
            result[aid] = {
                "name": str(db.get("name", "")),
                "phonenum": str(db.get("agentphone", "")),
                "id": aid,
                "phone": PHONE_MAP.get(ami_data["phone"], "phoneunknown"),
                "state": db.get("state", "unknown") if ami_data["member"] != "online" else "online",
                "dateofchange": str(db.get("changed", ""))
            }

        log.info(f"Returning {len(result)} agents")
        self._respond(200, result)

    def _respond(self, status: int, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.debug("%s", format % args)

def start_listener(host: str, port: int) -> threading.Thread:
    server = ThreadingHTTPServer((host, port), QueueHandler)
    log.info(f"HTTP listener started on {host}:{port}")
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t
