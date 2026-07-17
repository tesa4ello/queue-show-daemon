# db/client.py
import queue as _queue
import pymysql
from contextlib import contextmanager
from typing import List, Dict
from logger import setup_logger

log = setup_logger("db.client")

# Размер пула соединений. HTTP-сервер многопоточный (поток на запрос),
# поэтому одно общее соединение под глобальным Lock сериализовало все запросы —
# именно это давало «блокировки». Небольшой пул устраняет сериализацию.
DEFAULT_POOL_SIZE = 5


class DBClient:
    """Потокобезопасный пул соединений MySQL.

    Интерфейс совместим с прежним DBClient (get_agents_by_ids / close), но внутри —
    пул соединений: каждый поток берёт своё соединение, обращения не блокируют
    друг друга. Соединения проверяются/переподключаются при выдаче из пула.
    """

    def __init__(self, host, port, user, password, database, pool_size=DEFAULT_POOL_SIZE, timeout=10):
        self._cfg = {
            "host": host, "port": port, "user": user,
            "password": password, "database": database,
            "cursorclass": pymysql.cursors.DictCursor, "autocommit": True,
            "connect_timeout": timeout, "read_timeout": timeout, "write_timeout": timeout,
        }
        self._pool: "_queue.Queue" = _queue.Queue(maxsize=pool_size)
        # Слоты изначально «ленивые» (None) — соединения создаются по мере надобности.
        for _ in range(pool_size):
            self._pool.put(None)
        # Проверяем конфигурацию сразу, чтобы демон не стартовал с нерабочей БД.
        conn = self._new_conn()
        conn.close()
        log.info(f"MySQL pool ready (size={pool_size})")

    def _new_conn(self):
        try:
            return pymysql.connect(**self._cfg)
        except Exception as e:
            log.error(f"MySQL connection failed: {e}")
            raise

    @contextmanager
    def _connection(self):
        conn = self._pool.get()  # ждём свободный слот
        try:
            if conn is None or not conn.open:
                conn = self._new_conn()
            else:
                conn.ping(reconnect=True)  # оживляем «протухшее» соединение
            yield conn
        except Exception:
            # Битое соединение не возвращаем в пул, но слот восстанавливаем (None).
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            self._pool.put(None)
            raise
        else:
            self._pool.put(conn)

    def get_agents_by_ids(self, agent_ids: List[str]) -> Dict[str, Dict]:
        if not agent_ids:
            return {}
        placeholders = ",".join(["%s"] * len(agent_ids))
        sql = (
            "SELECT agentid, state, agentphone, name, dateofchange AS changed "
            f"FROM queue_agents WHERE agentid IN ({placeholders})"
        )
        try:
            with self._connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(agent_ids))
                    rows = cur.fetchall()
            return {str(row["agentid"]): row for row in rows}
        except Exception as e:
            log.error(f"DB query failed: {e}")
            return {}

    def close(self):
        while True:
            try:
                conn = self._pool.get_nowait()
            except _queue.Empty:
                break
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        log.info("MySQL pool closed")
