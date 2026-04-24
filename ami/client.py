# ami/client.py
import urllib.request
import urllib.parse
import http.cookiejar
import secrets
import threading
import time
from typing import Optional, Dict, Any

from config import cfg
from logger import setup_logger
from .parser import parse_mxml_response, AMIResponse

log = setup_logger("ami.client")

class AMIClient:
    """Клиент к Asterisk HTTP-AMI (mxml интерфейс) с поддержкой сессий."""
    
    def __init__(self, host: str, port: int, user: str, secret: str, 
                 timeout: int = 10, keepalive_interval: int = 30):
        self.base_url = f"http://{host}:{port}/mxml"
        self.user = user
        self.secret = secret
        self.timeout = timeout
        self.keepalive_interval = keepalive_interval
        
        # CookieJar для сохранения сессии
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )
        
        self._authenticated = False
        self._stop_keepalive = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def _generate_action_id(self) -> str:
        return f"queue-proxy-{secrets.token_hex(3)}"
    
    def _build_params(self, action: str, params: Optional[Dict] = None) -> Dict:
        result = {
            "action": action,
            "actionID": self._generate_action_id()
        }
        if params:
            result.update(params)
        return result
    
    def _request(self, action: str, params: Optional[Dict] = None) -> AMIResponse:
        """Отправить GET-запрос к mxml с сохранёнными куками."""
        full_params = self._build_params(action, params)
        query = urllib.parse.urlencode(full_params)
        url = f"{self.base_url}?{query}"
        
        log.debug(f"AMI -> {action} (actionID={full_params['actionID']})")
        req = urllib.request.Request(url, method="GET")
        
        with self._opener.open(req, timeout=self.timeout) as resp:
            raw = resp.read()
        return parse_mxml_response(raw)
    
    def login(self) -> bool:
        """Выполнить авторизацию."""
        resp = self._request("login", {
            "username": self.user,
            "secret": self.secret
        })
        
        if resp.success and resp.response_type == "Success":
            with self._lock:
                self._authenticated = True
            log.info("AMI authentication accepted")
            return True
        elif resp.response_type == "Error" and "Authentication failed" in resp.message:
            log.error(f"AMI authentication failed: {resp.message}")
            return False
        else:
            log.warning(f"Unexpected login response: {resp}")
            return False
    
    def logoff(self) -> bool:
        """Завершить сессию."""
        resp = self._request("logoff")
        
        if resp.response_type == "Goodbye":
            log.info("AMI session closed")
            with self._lock:
                self._authenticated = False
            # Очистить куки после логаута
            self._cookie_jar.clear()
            return True
        else:
            log.warning(f"Unexpected logoff response: {resp}")
            return False
    
    def ping(self) -> bool:
        """Отправить ping, вернуть True если получили Pong."""
        resp = self._request("ping")
        
        if resp.extra.get("ping") == "Pong":
            log.debug("AMI pong received")
            return True
        elif resp.response_type == "Error" and "Permission denied" in resp.message:
            log.warning("AMI session expired (Permission denied)")
            with self._lock:
                self._authenticated = False
            self._cookie_jar.clear()  # сбросить невалидные куки
            return False
        else:
            log.warning(f"Unexpected ping response: {resp}")
            return False
    
    def command(self, command: str) -> AMIResponse:
        """Выполнить CLI-команду через AMI."""
        return self._request("command", {"command": command})
    
    def _keepalive_loop(self):
        """Фоновый цикл отправки ping."""
        log.info(f"Keepalive started (interval={self.keepalive_interval}s)")
        while not self._stop_keepalive.is_set():
            if self._stop_keepalive.wait(timeout=self.keepalive_interval):
                break
            if not self._authenticated:
                log.debug("Not authenticated, attempting re-login...")
                if not self.login():
                    log.warning("Re-login failed, will retry later")
                    continue
            if not self.ping():
                log.warning("Ping failed, attempting re-login...")
                self.login()
    
    def start(self) -> bool:
        """Инициализировать соединение: логин + запуск keepalive."""
        if not self.login():
            return False
        
        self._stop_keepalive.clear()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, daemon=True, name="ami-keepalive"
        )
        self._keepalive_thread.start()
        return True
    
    def stop(self):
        """Корректно завершить: остановить keepalive и отправить logoff."""
        log.info("Stopping AMI client...")
        self._stop_keepalive.set()
        
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=2.0)
        
        if self._authenticated:
            try:
                self.logoff()
            except Exception as e:
                log.warning(f"Error during logoff: {e}")
        
        self._authenticated = False
        log.info("AMI client stopped")
    
    @property
    def authenticated(self) -> bool:
        with self._lock:
            return self._authenticated
