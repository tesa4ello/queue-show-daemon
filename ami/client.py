# ami/client.py
import urllib.request
import urllib.parse
import http.cookiejar
import secrets
import threading
from typing import Optional, Dict, List
from config import cfg
from logger import setup_logger
from .parser import parse_rawman_response, AMIResponse, parse_agents

log = setup_logger("ami.client")

class AMIClient:
    def __init__(self, host, port, user, secret, timeout=10, keepalive_interval=30):
        self.base_url = f"http://{host}:{port}/rawman"
        self.user = user
        self.secret = secret
        self.timeout = timeout
        self.keepalive_interval = keepalive_interval
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))
        self._authenticated = False
        self._stop_keepalive = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _generate_action_id(self):
        return f"queue-proxy-{secrets.token_hex(3)}"

    def _request(self, action: str, params: Optional[Dict] = None, retry: bool = True) -> AMIResponse:
        data = {"Action": action, "ActionID": self._generate_action_id()}
        if params:
            data.update(params)
        payload = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(self.base_url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        log.debug(f"AMI -> {action}")

        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
            parsed = parse_rawman_response(raw)
        except Exception as e:
            log.error(f"AMI request failed: {e}")
            return AMIResponse(False, "Error", str(e), None, {}, [])

        # 🔁 Авто-реавторизация при Permission denied
        if retry and action not in ("Login", "Logoff"):
            msg = parsed.message or ""
            if parsed.response_type == "Error" and "permission denied" in msg.lower():
                log.warning("Permission denied, session expired. Re-authenticating...")
                with self._lock:
                    self._authenticated = False
                self._cookie_jar.clear()
                if self.login():
                    return self._request(action, params, retry=False)  # Повторяем 1 раз
                else:
                    log.error("Re-authentication failed after Permission denied")

        return parsed

    def login(self) -> bool:
        resp = self._request("Login", {"Username": self.user, "Secret": self.secret}, retry=False)
        if resp.success and "accepted" in (resp.message or "").lower():
            with self._lock: self._authenticated = True
            log.info("AMI authentication accepted")
            return True
        log.error(f"AMI auth failed: {resp.message}")
        return False

    def logoff(self) -> bool:
        resp = self._request("Logoff", retry=False)
        if resp.response_type == "Goodbye" or "goodbye" in (resp.message or "").lower():
            log.info("AMI session closed")
            with self._lock: self._authenticated = False
            self._cookie_jar.clear()
            return True
        return False

    def ping(self) -> bool:
        resp = self._request("Ping")
        return resp.headers.get("Ping", "").lower() == "pong"

    def queue_show(self, queue_name: str) -> List[Dict]:
        resp = self._request("Command", {"Command": f"queue show {queue_name}"})
        if not resp.success:
            log.error(f"queue show {queue_name} failed: {resp.message}")
            return []
        return parse_agents(resp.output_lines)

    def _keepalive_loop(self):
        log.info(f"Keepalive started (interval={self.keepalive_interval}s)")
        while not self._stop_keepalive.is_set():
            if self._stop_keepalive.wait(timeout=self.keepalive_interval):
                break
            if not self._authenticated:
                if not self.login():
                    log.warning("Re-login failed in keepalive")
                    continue
            if not self.ping():
                log.warning("Ping failed, session likely expired. Forcing re-login...")
                with self._lock: self._authenticated = False
                self._cookie_jar.clear()
                self.login()

    def start(self) -> bool:
        if not self.login(): return False
        self._stop_keepalive.clear()
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True, name="ami-keepalive")
        self._keepalive_thread.start()
        return True

    def stop(self):
        log.info("Stopping AMI client...")
        self._stop_keepalive.set()
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=2.0)
        if self._authenticated:
            try: self.logoff()
            except Exception as e: log.warning(f"Logoff error: {e}")
        self._authenticated = False
        log.info("AMI client stopped")

    @property
    def authenticated(self) -> bool:
        with self._lock: return self._authenticated
