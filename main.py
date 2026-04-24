# main.py
#!/usr/bin/env python3
import signal, sys, threading, time
from logger import setup_logger
from config import cfg
from listener import start_listener
from ami import AMIClient

log = setup_logger("main")
shutdown_event = threading.Event()
ami_client: AMIClient = None

def signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name
    log.info(f"Received {sig_name}, shutting down...")
    shutdown_event.set()

def main():
    global ami_client
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 1. Инициализация AMI-клиента
    ami_client = AMIClient(
        host=cfg.AMI_HOST,
        port=cfg.AMI_PORT,
        user=cfg.AMI_USER,
        secret=cfg.AMI_PASS,
        timeout=cfg.AMI_TIMEOUT,
        keepalive_interval=cfg.KEEPALIVE_INTERVAL
    )
    
    if not ami_client.start():
        log.error("Failed to connect to Asterisk AMI, exiting")
        sys.exit(1)
    
    # 2. Запуск HTTP-слушателя
    start_listener(cfg.HTTP_HOST, cfg.HTTP_PORT)
    
    log.info("Daemon running. Waiting for shutdown signal...")
    
    # 3. Главный цикл
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except Exception as e:
        log.error(f"Main loop error: {e}")
    finally:
        # 4. Корректное завершение
        if ami_client:
            ami_client.stop()
        log.info("Daemon stopped gracefully")
        sys.exit(0)

if __name__ == "__main__":
    main()
