# config.py
import os
from pathlib import Path

def _load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))

_load_env()

class Config:
    PID_FILE = os.getenv("PID_FILE", "/var/run/asterisk-queue-proxy.pid")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FILE = os.getenv("LOG_FILE")
    
    # HTTP listener
    HTTP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    HTTP_PORT = int(os.getenv("APP_PORT", "8080"))
    
    # Asterisk HTTP-AMI (mxml)
    AMI_HOST = os.getenv("AMI_HOST", "127.0.0.1")
    AMI_PORT = int(os.getenv("AMI_PORT", "8088"))
    AMI_USER = os.getenv("AMI_USER", "admin")
    AMI_PASS = os.getenv("AMI_PASS", "secret")
    AMI_TIMEOUT = int(os.getenv("AMI_TIMEOUT", "10"))
    KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "30"))

cfg = Config()
