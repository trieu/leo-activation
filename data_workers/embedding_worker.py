import time
import psycopg2
import psycopg2.extras
import numpy as np

DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432,
}

VECTOR_DIM = 1536


def fake_embedding_generator(text: str) -> list[float]:
    """
    Replace with real embedding call (OpenAI, Cohere, etc.)
    """
    np.random.seed(abs(hash(text)) % (2**32))
    return np.random.rand(VECTOR_DIM).tolist()


def fetch_job(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            WITH job AS (
                SELECT job_id, tenant_id, event_id
                FROM embedding_job
                WHERE status = 'pending'
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE embedding_job
            SET status = 'processing',
                locked_at = now()
            FROM job
            WHERE embedding_job.job_id = job.job_id
            RETURNING job.*;
        """)
        return cur.fetchone()


def process_job(conn, job):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT event_name, event_description
            FROM marketing_event
            WHERE tenant_id = %s AND event_id = %s;
        """, (job["tenant_id"], job["event_id"]))

        row = cur.fetchone()
        if not row:
            return

        text = f"{row[0]} {row[1] or ''}"
        embedding = fake_embedding_generator(text)

        cur.execute("""
            UPDATE marketing_event
            SET embedding = %s,
                embedding_status = 'ready',
                embedding_updated_at = now()
            WHERE tenant_id = %s AND event_id = %s;
        """, (embedding, job["tenant_id"], job["event_id"]))

        cur.execute("""
            UPDATE embedding_job
            SET status = 'done'
            WHERE job_id = %s;
        """, (job["job_id"],))

    conn.commit()


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    print("Embedding worker started...")

    while True:
        job = fetch_job(conn)
        if job:
            process_job(conn, job)
        else:
            time.sleep(2)


if __name__ == "__main__":
    main()
