"""Agent board: a tiny MCP server that lets two AI agents on this PC talk.

Purpose
    Claude Code and Antigravity (Gemini) both run this server as a local
    stdio MCP server. Every instance opens the same SQLite file, so a message
    one agent posts is read by the other. Besides messages the board holds
    locks (who owns the Unreal editor, a map, a file) and a small task list,
    so the two agents do not run heavy jobs at the same time or edit the
    same files.

Command (started by the MCP client, not by hand)
    python Tools/agent_board/board_mcp.py --agent claude
    python Tools/agent_board/board_mcp.py --agent antigravity
    Optional: --db <path> (default: <repo>/Saved/AgentBoard/board.db).
    The agent name can also come from the AGENT_BOARD_NAME variable.
    Self-test without a client: python Tools/agent_board/board_mcp.py --selftest

Inputs
    JSON-RPC 2.0 messages on stdin, one per line (MCP stdio transport).

Outputs
    JSON-RPC responses on stdout, one per line; diagnostics on stderr.
    The shared board lives in Saved/AgentBoard/board.db (git-ignored).

Pure standard library (Python 3.10+); no MCP SDK needed.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import traceback
from pathlib import Path

SERVER_NAME = "agent-board"
SERVER_VERSION = "1.0.0"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO / "Saved" / "AgentBoard" / "board.db"
MAX_WAIT_S = 120
TASK_STATES = ("open", "claimed", "done", "dropped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cursors (
    agent TEXT PRIMARY KEY,
    last_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS locks (
    resource TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    purpose TEXT NOT NULL,
    ts REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    author TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    assignee TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    note TEXT NOT NULL DEFAULT '',
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    last_seen REAL NOT NULL,
    pid INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
"""


def log(*parts):
    print("[agent-board]", *parts, file=sys.stderr, flush=True)


def stamp(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def ago(t):
    s = max(0, int(time.time() - t))
    if s < 60:
        return "%ds ago" % s
    if s < 3600:
        return "%dm ago" % (s // 60)
    return "%dh%02dm ago" % (s // 3600, (s % 3600) // 60)


class ToolError(Exception):
    pass


class Board:
    def __init__(self, db_path, agent):
        self.agent = agent
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript(SCHEMA)
        self.touch()

    # -- helpers ---------------------------------------------------------
    def touch(self, note=None):
        now = time.time()
        if note is None:
            self.db.execute(
                "INSERT INTO agents(name,last_seen,pid) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen, pid=excluded.pid",
                (self.agent, now, os.getpid()))
        else:
            self.db.execute(
                "INSERT INTO agents(name,last_seen,pid,note) VALUES(?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen, "
                "pid=excluded.pid, note=excluded.note",
                (self.agent, now, os.getpid(), note))

    def cursor(self):
        row = self.db.execute("SELECT last_id FROM cursors WHERE agent=?", (self.agent,)).fetchone()
        return row["last_id"] if row else 0

    def set_cursor(self, last_id):
        self.db.execute(
            "INSERT INTO cursors(agent,last_id) VALUES(?,?) "
            "ON CONFLICT(agent) DO UPDATE SET last_id=MAX(last_id, excluded.last_id)",
            (self.agent, last_id))

    def unread_rows(self, limit):
        return self.db.execute(
            "SELECT * FROM messages WHERE id>? AND sender<>? AND recipient IN ('all', ?) "
            "ORDER BY id LIMIT ?", (self.cursor(), self.agent, self.agent, limit)).fetchall()

    def purge_locks(self):
        self.db.execute("DELETE FROM locks WHERE expires<?", (time.time(),))

    @staticmethod
    def fmt_msg(r):
        to = "" if r["recipient"] == "all" else " -> %s" % r["recipient"]
        topic = " [%s]" % r["topic"] if r["topic"] else ""
        return "#%d %s %s%s%s:\n%s" % (r["id"], stamp(r["ts"]), r["sender"], to, topic, r["text"])

    @staticmethod
    def fmt_task(r):
        who = " @%s" % r["assignee"] if r["assignee"] else ""
        line = "#%d [%s]%s %s (by %s, %s)" % (r["id"], r["status"], who, r["title"], r["author"],
                                              stamp(r["updated"]))
        if r["details"]:
            line += "\n    " + r["details"].replace("\n", "\n    ")
        if r["note"]:
            line += "\n    note: " + r["note"].replace("\n", "\n    ")
        return line

    # -- tools -----------------------------------------------------------
    def status(self, note=None):
        self.touch(note)
        self.purge_locks()
        unread = len(self.unread_rows(1000))
        lines = ["You are '%s'. Unread messages: %d." % (self.agent, unread)]
        lines.append("Agents:")
        for r in self.db.execute("SELECT * FROM agents ORDER BY name"):
            extra = " - %s" % r["note"] if r["note"] else ""
            lines.append("  %s (seen %s)%s" % (r["name"], ago(r["last_seen"]), extra))
        locks = self.db.execute("SELECT * FROM locks ORDER BY resource").fetchall()
        lines.append("Locks:" if locks else "Locks: none")
        for r in locks:
            lines.append("  %s held by %s: %s (expires %s)" % (r["resource"], r["owner"], r["purpose"],
                                                             stamp(r["expires"])))
        tasks = self.db.execute(
            "SELECT * FROM tasks WHERE status IN ('open','claimed') ORDER BY id").fetchall()
        lines.append("Open tasks:" if tasks else "Open tasks: none")
        lines += ["  " + self.fmt_task(r).replace("\n", "\n  ") for r in tasks]
        return "\n".join(lines)

    def post_message(self, text, to="all", topic=""):
        text = (text or "").strip()
        if not text:
            raise ToolError("text is empty")
        to = (to or "all").strip() or "all"
        if to == self.agent:
            raise ToolError("cannot send a message to yourself")
        cur = self.db.execute(
            "INSERT INTO messages(ts,sender,recipient,topic,text) VALUES(?,?,?,?,?)",
            (time.time(), self.agent, to, (topic or "").strip(), text))
        return "Posted message #%d to %s." % (cur.lastrowid, to)

    def read_messages(self, unread_only=True, limit=20, mark_read=True):
        limit = max(1, min(int(limit or 20), 200))
        if unread_only:
            rows = self.unread_rows(limit)
        else:
            rows = list(reversed(self.db.execute(
                "SELECT * FROM messages WHERE recipient IN ('all', ?) OR sender=? "
                "ORDER BY id DESC LIMIT ?", (self.agent, self.agent, limit)).fetchall()))
        if not rows:
            return "No unread messages." if unread_only else "The board has no messages."
        if mark_read:
            self.set_cursor(max(r["id"] for r in rows))
        left = len(self.unread_rows(1000))
        out = "\n\n".join(self.fmt_msg(r) for r in rows)
        if left:
            out += "\n\n(%d more unread)" % left
        return out

    def wait_for_message(self, timeout_s=60):
        timeout_s = max(1, min(int(timeout_s or 60), MAX_WAIT_S))
        end = time.time() + timeout_s
        while True:
            if self.unread_rows(1):
                return self.read_messages(True, 20, True)
            if time.time() >= end:
                return "No message arrived in %d s." % timeout_s
            time.sleep(1.0)

    def lock(self, resource, purpose, ttl_min=60):
        resource = (resource or "").strip()
        if not resource:
            raise ToolError("resource is empty")
        ttl_min = max(1, min(float(ttl_min or 60), 24 * 60))
        now = time.time()
        self.purge_locks()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT * FROM locks WHERE resource=?", (resource,)).fetchone()
            if row and row["owner"] != self.agent:
                self.db.execute("ROLLBACK")
                return ("DENIED: %s is held by %s since %s for: %s (expires %s). "
                        "Ask them with post_message or wait." % (
                            resource, row["owner"], stamp(row["ts"]), row["purpose"],
                            stamp(row["expires"])))
            self.db.execute(
                "INSERT OR REPLACE INTO locks(resource,owner,purpose,ts,expires) VALUES(?,?,?,?,?)",
                (resource, self.agent, (purpose or "").strip(), row["ts"] if row else now,
                 now + ttl_min * 60))
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        verb = "Renewed" if row else "Locked"
        return "%s %s until %s." % (verb, resource, stamp(now + ttl_min * 60))

    def unlock(self, resource, force=False):
        self.purge_locks()
        row = self.db.execute("SELECT * FROM locks WHERE resource=?", (resource,)).fetchone()
        if not row:
            return "%s was not locked." % resource
        if row["owner"] != self.agent and not force:
            raise ToolError("%s is held by %s; pass force=true only if the user said so"
                            % (resource, row["owner"]))
        self.db.execute("DELETE FROM locks WHERE resource=?", (resource,))
        return "Unlocked %s (was held by %s)." % (resource, row["owner"])

    def list_locks(self):
        self.purge_locks()
        rows = self.db.execute("SELECT * FROM locks ORDER BY resource").fetchall()
        if not rows:
            return "No locks."
        return "\n".join("%s held by %s since %s: %s (expires %s)" % (
            r["resource"], r["owner"], stamp(r["ts"]), r["purpose"], stamp(r["expires"])) for r in rows)

    def add_task(self, title, details="", assignee=""):
        title = (title or "").strip()
        if not title:
            raise ToolError("title is empty")
        now = time.time()
        assignee = (assignee or "").strip()
        cur = self.db.execute(
            "INSERT INTO tasks(ts,author,title,details,assignee,status,updated) VALUES(?,?,?,?,?,?,?)",
            (now, self.agent, title, (details or "").strip(), assignee,
             "claimed" if assignee else "open", now))
        return "Added task #%d." % cur.lastrowid

    def claim_task(self, task_id):
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone()
        if not row:
            raise ToolError("no task #%s" % task_id)
        if row["status"] == "claimed" and row["assignee"] not in ("", self.agent):
            return "DENIED: task #%d is claimed by %s." % (row["id"], row["assignee"])
        if row["status"] in ("done", "dropped"):
            return "DENIED: task #%d is already %s." % (row["id"], row["status"])
        self.db.execute("UPDATE tasks SET assignee=?, status='claimed', updated=? WHERE id=?",
                        (self.agent, time.time(), row["id"]))
        return "Claimed task #%d." % row["id"]

    def update_task(self, task_id, status, note=""):
        if status not in TASK_STATES:
            raise ToolError("status must be one of %s" % ", ".join(TASK_STATES))
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone()
        if not row:
            raise ToolError("no task #%s" % task_id)
        assignee = row["assignee"]
        if status == "open":
            assignee = ""
        elif status == "claimed" and not assignee:
            assignee = self.agent
        self.db.execute("UPDATE tasks SET status=?, assignee=?, note=?, updated=? WHERE id=?",
                        (status, assignee, (note or row["note"]).strip(), time.time(), row["id"]))
        return "Task #%d is now %s." % (row["id"], status)

    def list_tasks(self, status="active"):
        status = (status or "active").strip()
        if status == "active":
            rows = self.db.execute(
                "SELECT * FROM tasks WHERE status IN ('open','claimed') ORDER BY id").fetchall()
        elif status == "all":
            rows = self.db.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 50").fetchall()
        elif status in TASK_STATES:
            rows = self.db.execute("SELECT * FROM tasks WHERE status=? ORDER BY id DESC LIMIT 50",
                                   (status,)).fetchall()
        else:
            raise ToolError("status must be active, all or one of %s" % ", ".join(TASK_STATES))
        return "\n".join(self.fmt_task(r) for r in rows) if rows else "No tasks."


def schema(props, required=()):
    # Plain JSON Schema only (type/description/enum): Gemini rejects keywords like "default".
    return {"type": "object", "properties": props, "required": list(required)}


S = lambda d: {"type": "string", "description": d}  # noqa: E731
I = lambda d: {"type": "integer", "description": d}  # noqa: E731
B = lambda d: {"type": "boolean", "description": d}  # noqa: E731

TOOLS = [
    ("board_status",
     "Show who you are, unread message count, other agents and when they were last seen, "
     "active locks and open tasks. Call it at the start of a work session.",
     schema({"note": S("Optional: what you are working on now, shown to the other agent.")}),
     lambda b, a: b.status(a.get("note"))),
    ("post_message",
     "Send a message to the other agent(s) on this PC. Use for hand-offs, questions, and "
     "announcing what you are about to change.",
     schema({"text": S("The message."),
             "to": S("Recipient agent name (e.g. 'claude', 'antigravity') or 'all'. Default 'all'."),
             "topic": S("Optional short topic, e.g. 'outskirts' or 'build'.")}, ["text"]),
     lambda b, a: b.post_message(a.get("text"), a.get("to", "all"), a.get("topic", ""))),
    ("read_messages",
     "Read messages addressed to you or to 'all'. By default returns only unread ones and "
     "marks them read.",
     schema({"unread_only": B("Default true. False shows recent history including your own."),
             "limit": I("Maximum messages, default 20."),
             "mark_read": B("Default true.")}),
     lambda b, a: b.read_messages(a.get("unread_only", True), a.get("limit", 20), a.get("mark_read", True))),
    ("wait_for_message",
     "Block until a new message for you arrives or the timeout ends (max 120 s), then return it. "
     "Use when you asked the other agent something and need the answer to continue.",
     schema({"timeout_s": I("Seconds to wait, default 60, max 120.")}),
     lambda b, a: b.wait_for_message(a.get("timeout_s", 60))),
    ("lock",
     "Take or renew an exclusive lock on a shared resource before using it. Conventional names: "
     "'unreal-editor' (any UnrealEditor or commandlet run), 'build' (C++ build), 'map:<name>', "
     "'file:<repo path>', 'git' (commit/push). Returns DENIED if another agent holds it.",
     schema({"resource": S("Resource name, e.g. 'unreal-editor' or 'file:Tools/bay/build_bay.py'."),
             "purpose": S("What you will do with it."),
             "ttl_min": I("Minutes until it expires on its own, default 60, max 1440.")},
            ["resource", "purpose"]),
     lambda b, a: b.lock(a.get("resource"), a.get("purpose", ""), a.get("ttl_min", 60))),
    ("unlock",
     "Release a lock you hold. force=true releases another agent's lock; only when the user said so.",
     schema({"resource": S("Resource name."), "force": B("Default false.")}, ["resource"]),
     lambda b, a: b.unlock(a.get("resource"), bool(a.get("force", False)))),
    ("list_locks", "List active locks.", schema({}), lambda b, a: b.list_locks()),
    ("add_task",
     "Add a task to the shared list. Give an assignee to hand it straight to an agent.",
     schema({"title": S("Short title."), "details": S("What done looks like, files involved."),
             "assignee": S("Optional agent name.")}, ["title"]),
     lambda b, a: b.add_task(a.get("title"), a.get("details", ""), a.get("assignee", ""))),
    ("claim_task", "Claim an open task so the other agent does not start it.",
     schema({"task_id": I("Task number.")}, ["task_id"]),
     lambda b, a: b.claim_task(a.get("task_id"))),
    ("update_task", "Change a task's status (open, claimed, done, dropped) and leave a note.",
     schema({"task_id": I("Task number."),
             "status": {"type": "string", "enum": list(TASK_STATES), "description": "New status."},
             "note": S("Result, commit hash, or why it was dropped.")}, ["task_id", "status"]),
     lambda b, a: b.update_task(a.get("task_id"), a.get("status"), a.get("note", ""))),
    ("list_tasks", "List tasks. status: 'active' (default: open+claimed), 'all', or one state.",
     schema({"status": S("active, all, open, claimed, done or dropped.")}),
     lambda b, a: b.list_tasks(a.get("status", "active"))),
]
TOOL_MAP = {t[0]: t for t in TOOLS}


class Server:
    def __init__(self, board):
        self.board = board

    def handle(self, msg):
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method is None:  # a response to something we never sent
            return None
        if mid is None:  # notification
            return None
        try:
            result = self.dispatch(method, params)
        except RpcError as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": e.code, "message": str(e)}}
        except Exception as e:  # noqa: BLE001
            log("error in", method, traceback.format_exc())
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def dispatch(self, method, params):
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Shared board between the AI agents working on this PC (you are '%s'). "
                    "Call board_status when you start, read_messages before big steps, lock "
                    "'unreal-editor' before running Unreal, and post_message to hand work over."
                    % self.board.agent),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s, _ in TOOLS]}
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name not in TOOL_MAP:
                raise RpcError(-32602, "unknown tool: %s" % name)
            self.board.touch()
            try:
                text = TOOL_MAP[name][3](self.board, args)
                return {"content": [{"type": "text", "text": text}], "isError": False}
            except (ToolError, ValueError, TypeError) as e:
                return {"content": [{"type": "text", "text": "Error: %s" % e}], "isError": True}
        if method in ("resources/list", "prompts/list"):
            return {method.split("/")[0]: []}
        raise RpcError(-32601, "method not found: %s" % method)

    def serve(self):
        log("started as '%s' on %s" % (self.board.agent, DB_IN_USE))
        stdin = sys.stdin.buffer
        out = sys.stdout.buffer
        for raw in stdin:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw.decode("utf-8-sig"))  # tolerate a BOM from Windows shells
            except ValueError:
                log("unparsable line:", raw[:120])
                reply = [{"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}]
            else:
                if isinstance(msg, list):
                    reply = [r for r in (self.handle(m) for m in msg) if r]
                else:
                    reply = [r for r in [self.handle(msg)] if r]
            for r in reply:
                out.write(json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n")
            out.flush()
        log("stdin closed, exiting")


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


DB_IN_USE = None


def selftest():
    import tempfile
    path = Path(tempfile.mkdtemp()) / "board.db"
    a, b = Board(path, "claude"), Board(path, "antigravity")
    assert "Posted" in a.post_message("hello", "antigravity", "test")
    assert "hello" in b.read_messages()
    assert b.read_messages() == "No unread messages."
    assert "Locked" in a.lock("unreal-editor", "build_bay")
    assert b.lock("unreal-editor", "x").startswith("DENIED")
    assert "Unlocked" in a.unlock("unreal-editor")
    assert "Locked" in b.lock("unreal-editor", "x")
    t = a.add_task("try it")
    assert "#1" in t and "Claimed" in b.claim_task(1)
    assert a.claim_task(1).startswith("DENIED")
    assert "done" in b.update_task(1, "done", "ok")
    print(a.status())
    print("selftest OK")


def main():
    global DB_IN_USE
    ap = argparse.ArgumentParser(description="Agent board MCP server")
    ap.add_argument("--agent", default=os.environ.get("AGENT_BOARD_NAME", ""))
    ap.add_argument("--db", default=os.environ.get("AGENT_BOARD_DB", str(DEFAULT_DB)))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    agent = args.agent.strip().lower()
    if not agent or agent == "all":
        ap.error("--agent is required (and cannot be 'all')")
    DB_IN_USE = args.db
    Server(Board(args.db, agent)).serve()


if __name__ == "__main__":
    main()
