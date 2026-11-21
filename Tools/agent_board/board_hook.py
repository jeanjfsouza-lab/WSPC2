r"""Hook notifier for agent-board: injects new unread peer messages once per session.

Purpose
    Reads Saved/AgentBoard/board.db without advancing MCP read cursors, so
    Claude Code (UserPromptSubmit) and Antigravity (PreInvocation) are alerted
    once when new unread messages from the peer agent arrive.

Exact commands
    python "D:\Github\WSPC2\Tools\agent_board\board_hook.py" --agent claude
    python "D:\Github\WSPC2\Tools\agent_board\board_hook.py" --agent antigravity
    Optional: --db <path> (defaults to AGENT_BOARD_DB or ../../Saved/AgentBoard/board.db)

Inputs
    Hook JSON payload on stdin (session_id for Claude Code; conversationId for Antigravity).
    SQLite database at --db (tables: messages, cursors, locks; manages hook_notified).

Outputs
    Claude Code: plain-text summary on stdout when new unread messages exist; empty otherwise.
    Antigravity: JSON {"injectSteps": [{"systemMessage": {"systemMessage": ...}}]} when new
    unread messages exist; "{}" otherwise.
"""

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO / "Saved" / "AgentBoard" / "board.db"


def emit_empty(agent):
    if agent == "antigravity":
        print("{}")
    sys.exit(0)


def read_stdin_payload(timeout_s=0.25):
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    result = []

    def _reader():
        try:
            result.append(sys.stdin.read())
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout_s)
    if not result:
        return {}
    raw = (result[0] or "").lstrip("\ufeff").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def truncate(text, limit=300):
    single = " ".join(str(text or "").split())
    if len(single) <= limit:
        return single
    return single[: limit - 3] + "..."


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="agent-board unread message hook notifier")
    ap.add_argument("--agent", required=True, choices=["claude", "antigravity"])
    ap.add_argument("--db", default=os.environ.get("AGENT_BOARD_DB", str(DEFAULT_DB)))
    args = ap.parse_args()

    payload = read_stdin_payload()
    db_path = Path(args.db)
    if not db_path.exists():
        emit_empty(args.agent)

    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")

        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('messages', 'cursors', 'locks')"
            )
        }
        if "messages" not in tables or "cursors" not in tables:
            emit_empty(args.agent)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hook_notified (
                client_key TEXT PRIMARY KEY,
                last_id INTEGER NOT NULL,
                ts REAL NOT NULL
            )
            """
        )

        cursor_row = conn.execute(
            "SELECT last_id FROM cursors WHERE agent=?", (args.agent,)
        ).fetchone()
        cursor_id = int(cursor_row["last_id"]) if cursor_row else 0

        if args.agent == "antigravity":
            session_id = str(payload.get("conversationId") or "default")
        else:
            session_id = str(payload.get("session_id") or "default")
        client_key = f"{args.agent}:{session_id}"

        notified_row = conn.execute(
            "SELECT last_id FROM hook_notified WHERE client_key=?", (client_key,)
        ).fetchone()
        notified_id = int(notified_row["last_id"]) if notified_row else 0

        since_id = max(cursor_id, notified_id)
        rows = conn.execute(
            """
            SELECT id, ts, sender, recipient, topic, text
            FROM messages
            WHERE id > ? AND sender <> ? AND recipient IN ('all', ?)
            ORDER BY id ASC
            LIMIT 20
            """,
            (since_id, args.agent, args.agent),
        ).fetchall()

        if not rows:
            emit_empty(args.agent)

        max_id = max(int(r["id"]) for r in rows)
        now = time.time()
        conn.execute(
            """
            INSERT INTO hook_notified(client_key, last_id, ts)
            VALUES(?, ?, ?)
            ON CONFLICT(client_key) DO UPDATE SET
                last_id = MAX(hook_notified.last_id, excluded.last_id),
                ts = excluded.ts
            """,
            (client_key, max_id, now),
        )

        peer_locks = []
        if "locks" in tables:
            peer_locks = conn.execute(
                "SELECT resource, owner, purpose, expires FROM locks WHERE expires > ? AND owner <> ? ORDER BY resource",
                (now, args.agent),
            ).fetchall()

        lines = [f"[agent-board] {len(rows)} unread message(s) for {args.agent}:"]
        for r in rows:
            topic_part = f" [{r['topic']}]" if r["topic"] else ""
            lines.append(f"- #{r['id']} {r['sender']}{topic_part}: {truncate(r['text'], 300)}")

        if peer_locks:
            lines.append("Active peer locks:")
            for lk in peer_locks:
                purpose_part = f": {truncate(lk['purpose'], 120)}" if lk["purpose"] else ""
                lines.append(f"- {lk['resource']} (by {lk['owner']}){purpose_part}")

        lines.append("Call read_messages / post_message on the agent-board MCP to read full details and reply.")
        summary = "\n".join(lines)

        if args.agent == "claude":
            print(summary)
        else:
            print(
                json.dumps(
                    {"injectSteps": [{"systemMessage": {"systemMessage": summary}}]},
                    ensure_ascii=False,
                )
            )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
