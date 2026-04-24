# main.py
#!/usr/bin/env python3
import signal
import sys
import threading
from logger import setup_logger
from config import cfg
from listener import start_listener, set_clients
from ami import AMIClient
from db import DBClient  # <-- новое

log = setup_logger("main")
shutdown_event = threading.Event()
ami_client = None
db_client = None  # <-- новое

def signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name
    log.info(f"Received {sig_name}, shutting down...")
    shutdown_event.set()

def main():
    global ami_client, db_client
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 1. DB
    try:
        db_client = DBClient(cfg.MYSQL_HOST, cfg.MYSQL_PORT, cfg.MYSQL_USER, cfg.MYSQL_PASS, cfg.MYSQL_BASE)
    except Exception as e:
        log.critical(f"Cannot start without DB: {e}")
        sys.exit(1)

    # 2. AMI
    ami_client = AMIClient(cfg.AMI_HOST, cfg.AMI_PORT, cfg.AMI_USER, cfg.AMI_PASS,
                           cfg.AMI_TIMEOUT, cfg.KEEPALIVE_INTERVAL)
    if not ami_client.start():
        log.error("Failed to connect to Asterisk AMI")
        sys.exit(1)

    set_clients(ami_client,db_client)
    start_listener(cfg.HTTP_HOST, cfg.HTTP_PORT)

    log.info("Daemon running")
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except Exception as e:
        log.error(f"Main loop error: {e}")
    finally:
        if ami_client: ami_client.stop()
        if db_client: db_client.close()  # <-- новое
        log.info("Daemon stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
