# ami/client.py
import urllib.request
import urllib.parse
import http.cookiejar
import secrets
import threading
import time
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

    def _request(self, action: str, params: Optional[Dict] = None) -> AMIResponse:
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
            return parse_rawman_response(raw)
        except Exception as e:
            log.error(f"AMI request failed: {e}")
            return AMIResponse(False, "Error", str(e), None, {}, [])

    def login(self) -> bool:
        resp = self._request("Login", {"Username": self.user, "Secret": self.secret})
        if resp.success and "accepted" in resp.message.lower():
            with self._lock: self._authenticated = True
            log.info("AMI authentication accepted")
            return True
        log.error(f"AMI auth failed: {resp.message}")
        return False

    def logoff(self) -> bool:
        resp = self._request("Logoff")
        if resp.response_type == "Goodbye" or "goodbye" in resp.message.lower():
            log.info("AMI session closed")
            with self._lock: self._authenticated = False
            self._cookie_jar.clear()
            return True
        return False

    def ping(self) -> bool:
        resp = self._request("Ping")
        if resp.headers.get("Ping", "").lower() == "pong":
            log.debug("AMI pong received")
            return True
        if resp.response_type == "Error" and "permission denied" in resp.message.lower():
            log.warning("AMI session expired")
            with self._lock: self._authenticated = False
            self._cookie_jar.clear()
            return False
        return False

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
                    log.warning("Re-login failed")
                    continue
            if not self.ping():
                log.warning("Ping failed, re-login...")
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
