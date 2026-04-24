# db/client.py
import pymysql
import threading
from logger import setup_logger

log = setup_logger("db.client")

class DBClient:
    def __init__(self, host, port, user, password, database):
        self._cfg = {
            "host": host, "port": port, "user": user,
            "password": password, "database": database,
            "cursorclass": pymysql.cursors.DictCursor, "autocommit": True
        }
        self.conn = None
        self._lock = threading.Lock()
        self.connect()

    def connect(self):
        try:
            self.conn = pymysql.connect(**self._cfg)
            log.info("Connected to MySQL")
        except Exception as e:
            log.error(f"MySQL connection failed: {e}")
            raise

    def fetch(self, sql: str, params: tuple | None = None) -> list[dict]:
        with self._lock:
            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall()
            except pymysql.OperationalError:
                log.warning("MySQL disconnected, reconnecting...")
                self.connect()
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall()

    def get_agents_by_ids(self, agent_ids: list[str]) -> dict[str, dict]:
        if not agent_ids: return {}
        placeholders = ','.join(['%s'] * len(agent_ids))
        sql = f"SELECT agentid, state, agentphone, name, dateofchange AS changed FROM queue_agents WHERE agentid IN ({placeholders})"
        try:
            rows = self.fetch(sql, tuple(agent_ids))
            return {str(row['agentid']): row for row in rows}
        except Exception as e:
            log.error(f"DB query failed: {e}")
            return {}

    def close(self):
        if self.conn and self.conn.open:
            self.conn.close()
            log.info("MySQL connection closed")
