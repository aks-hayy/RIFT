"""Durable, immutable workload reviews, approvals, and run journals.

The store is deliberately not an evaluator or serving executor. The workload
controller consumes approvals, accounts for actions before execution, and
produces fresh acceptance evidence; persisted approvals alone are never
``VERIFIED``.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from typing import Any
import uuid

from .execution_policy import canonical_json, content_hash, require_within_policy, validate_envelope, validate_workload_contract


def _run_json_safe(value: Any) -> Any:
    """Normalize runtime-only values before journaling execution evidence.

    Backend probes and tuning diagnostics may return sets (for example a set
    of supported flags) or Path objects.  Workload contracts and approval
    hashes remain strict JSON, but run evidence is an observation boundary and
    must never fail a completed deployment merely because a diagnostic used a
    non-JSON Python container.
    """
    if isinstance(value, dict):
        return {str(key): _run_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_run_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_run_json_safe(item) for item in value]
        return sorted(normalized, key=lambda item: str(item))
    if isinstance(value, Path):
        return str(value)
    return value


class WorkloadStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workload_policies (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, hash TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(id, revision));
                CREATE TABLE IF NOT EXISTS workload_drafts (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, hash TEXT NOT NULL,
                    contract TEXT NOT NULL, provenance TEXT NOT NULL, questions TEXT NOT NULL,
                    created_at REAL NOT NULL, PRIMARY KEY(id, revision));
                CREATE TABLE IF NOT EXISTS workload_approvals (
                    id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, draft_revision INTEGER NOT NULL,
                    contract_hash TEXT NOT NULL, policy_id TEXT NOT NULL, policy_revision INTEGER NOT NULL,
                    envelope_hash TEXT NOT NULL, envelope TEXT NOT NULL, created_at REAL NOT NULL,
                    UNIQUE(draft_id, draft_revision));
                CREATE TABLE IF NOT EXISTS workload_action_reservations (
                    approval_id TEXT NOT NULL, action_id TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at REAL NOT NULL, PRIMARY KEY(approval_id, action_id));
                CREATE TABLE IF NOT EXISTS workload_runs (
                    id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, approval_id TEXT NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS workload_run_events (
                    run_id TEXT NOT NULL, sequence INTEGER NOT NULL, stage TEXT NOT NULL,
                    message TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY(run_id, sequence));
            """)

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(str(self.path), timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _revision(db, table, record_id):
        # Table names are internal constants, never request input.
        row = db.execute(f"SELECT MAX(revision) FROM {table} WHERE id=?", (record_id,)).fetchone()
        return row[0] or 0

    def save_policy(self, policy_id: str, value: dict, *, expected_revision: int) -> dict:
        if not policy_id or type(expected_revision) is not int:
            raise ValueError("policy id and expected revision are required")
        policy = validate_envelope(value)
        with self._transaction() as db:
            current = self._revision(db, "workload_policies", policy_id)
            if current != expected_revision:
                raise ValueError("stale policy revision")
            revision = current + 1
            digest = content_hash(policy)
            db.execute("INSERT INTO workload_policies VALUES(?,?,?,?)", (policy_id, revision, digest, canonical_json(policy)))
        return {"policy_id": policy_id, "revision": revision, "policy_hash": digest, "policy": policy}

    def get_policy(self, policy_id: str, *, revision: int | None = None) -> dict[str, Any]:
        with self._transaction() as db:
            current = self._revision(db, "workload_policies", policy_id)
            selected = current if revision is None else revision
            row = db.execute("SELECT * FROM workload_policies WHERE id=? AND revision=?", (policy_id, selected)).fetchone()
            if row is None:
                raise KeyError(policy_id)
        return {"policy_id": policy_id, "revision": selected, "policy_hash": row["hash"], "policy": json.loads(row["payload"])}

    def list_policies(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._transaction() as db:
            rows = db.execute("""SELECT p.* FROM workload_policies p
                JOIN (SELECT id, MAX(revision) revision FROM workload_policies GROUP BY id) latest
                  ON latest.id=p.id AND latest.revision=p.revision
                ORDER BY p.rowid DESC LIMIT ?""", (min(max(1, int(limit)), 500),)).fetchall()
        return [{"policy_id": row["id"], "revision": row["revision"], "policy_hash": row["hash"], "policy": json.loads(row["payload"])} for row in rows]

    def save_draft(self, contract: dict, *, provenance: dict, questions: list[str], draft_id: str | None = None, expected_revision: int = 0) -> dict:
        contract = validate_workload_contract(contract)
        if type(expected_revision) is not int or not isinstance(provenance, dict) or not isinstance(questions, list) or any(not isinstance(q, str) or not q.strip() for q in questions):
            raise ValueError("draft requires provenance, explicit questions, and integer expected revision")
        draft_id = draft_id or uuid.uuid4().hex
        with self._transaction() as db:
            current = self._revision(db, "workload_drafts", draft_id)
            if current != expected_revision:
                raise ValueError("stale draft revision")
            revision = current + 1
            digest = content_hash(contract)
            db.execute("INSERT INTO workload_drafts VALUES(?,?,?,?,?,?,?)", (draft_id, revision, digest, canonical_json(contract), canonical_json(provenance), canonical_json(questions), time.time()))
        return self.get_draft(draft_id, revision=revision)

    def get_draft(self, draft_id: str, *, revision: int | None = None) -> dict:
        with self._transaction() as db:
            current = self._revision(db, "workload_drafts", draft_id)
            revision = current if revision is None else revision
            row = db.execute("SELECT * FROM workload_drafts WHERE id=? AND revision=?", (draft_id, revision)).fetchone()
            if row is None:
                raise KeyError(draft_id)
            approval = db.execute("SELECT id FROM workload_approvals WHERE draft_id=? AND draft_revision=?", (draft_id, revision)).fetchone()
        provenance = json.loads(row["provenance"])
        compiler_meta = provenance.get("/_compiler") if isinstance(provenance, dict) else {}
        return {"draft_id": draft_id, "revision": revision, "contract_hash": row["hash"],
                "contract": json.loads(row["contract"]), "provenance": provenance,
                "questions": json.loads(row["questions"]),
                "warnings": list(compiler_meta.get("warnings") or []) if isinstance(compiler_meta, dict) else [],
                "unsupported_requirements": list(compiler_meta.get("unsupported_requirements") or []) if isinstance(compiler_meta, dict) else [],
                "limitations": list(compiler_meta.get("limitations") or []) if isinstance(compiler_meta, dict) else [],
                "status": "SUPERSEDED" if revision != current else "APPROVED" if approval else "COMPILED"}

    def list_drafts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return the newest revision of each draft for review screens."""
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._transaction() as db:
            rows = db.execute(
                """SELECT d.* FROM workload_drafts d
                   JOIN (SELECT id, MAX(revision) revision FROM workload_drafts GROUP BY id) latest
                     ON latest.id=d.id AND latest.revision=d.revision
                   ORDER BY d.created_at DESC LIMIT ?""",
                (min(limit, 500),),
            ).fetchall()
            approvals = {
                row["draft_id"]: row["draft_revision"]
                for row in db.execute("SELECT draft_id, draft_revision FROM workload_approvals")
            }
        result = []
        for row in rows:
            provenance = json.loads(row["provenance"])
            compiler_meta = provenance.get("/_compiler") if isinstance(provenance, dict) else {}
            result.append({
                "draft_id": row["id"],
                "revision": row["revision"],
                "contract_hash": row["hash"],
                "contract": json.loads(row["contract"]),
                "provenance": provenance,
                "questions": json.loads(row["questions"]),
                "warnings": list(compiler_meta.get("warnings") or []) if isinstance(compiler_meta, dict) else [],
                "unsupported_requirements": list(compiler_meta.get("unsupported_requirements") or []) if isinstance(compiler_meta, dict) else [],
                "limitations": list(compiler_meta.get("limitations") or []) if isinstance(compiler_meta, dict) else [],
                "status": "APPROVED" if approvals.get(row["id"]) == row["revision"] else "COMPILED",
            })
        return result

    def approve(self, draft_id: str, *, expected_revision: int, contract_hash: str, policy_id: str, policy_revision: int, envelope: dict, envelope_hash: str) -> dict:
        envelope = validate_envelope(envelope)
        if content_hash(envelope) != envelope_hash:
            raise ValueError("stale approval envelope hash")
        with self._transaction() as db:
            if expected_revision != self._revision(db, "workload_drafts", draft_id):
                raise ValueError("stale workload revision")
            row = db.execute("SELECT * FROM workload_drafts WHERE id=? AND revision=?", (draft_id, expected_revision)).fetchone()
            if row is None or row["hash"] != contract_hash:
                raise ValueError("stale workload contract hash")
            if json.loads(row["questions"]):
                raise ValueError("resolve review questions before approval")
            if policy_revision != self._revision(db, "workload_policies", policy_id):
                raise ValueError("stale saved policy revision")
            policy = db.execute("SELECT payload FROM workload_policies WHERE id=? AND revision=?", (policy_id, policy_revision)).fetchone()
            if policy is None:
                raise PermissionError("saved execution policy is required")
            require_within_policy(envelope, json.loads(policy["payload"]))
            contract = json.loads(row["contract"])
            if contract["policies"]["network"] == "offline" and envelope["network"] != "offline":
                raise PermissionError("approved envelope cannot relax workload offline requirement")
            existing = db.execute("SELECT * FROM workload_approvals WHERE draft_id=? AND draft_revision=?", (draft_id, expected_revision)).fetchone()
            if existing:
                if existing["envelope_hash"] != envelope_hash or existing["policy_id"] != policy_id or existing["policy_revision"] != policy_revision:
                    raise ValueError("this revision already has a different approval; create a new draft revision")
                approval_id = existing["id"]
            else:
                approval_id = uuid.uuid4().hex
                db.execute("INSERT INTO workload_approvals VALUES(?,?,?,?,?,?,?,?,?)", (approval_id, draft_id, expected_revision, contract_hash, policy_id, policy_revision, envelope_hash, canonical_json(envelope), time.time()))
        return {"approval_id": approval_id, "status": "APPROVED", "draft_id": draft_id, "revision": expected_revision,
                "contract_hash": contract_hash, "envelope_hash": envelope_hash, "deployment_started": False}

    def reserve_action(self, approval_id: str, action_id: str, *, action: str, target: str, download_bytes: int = 0, source: str | None = None, artifact_id: str | None = None) -> dict[str, Any]:
        """Reserve network bytes before an external action, idempotently.

        Counts pessimistically include reservations whose completion is unknown.
        A crash/retry must use the same action id; reopening the journal never
        replenishes budget. Target trust and process ownership are executor gates.
        """
        if not isinstance(action_id, str) or not action_id or type(download_bytes) is not int or download_bytes < 0:
            raise ValueError("action id and nonnegative byte reservation are required")
        if action != "download" and (download_bytes or source is not None or artifact_id is not None):
            raise ValueError("download accounting fields are only valid for download actions")
        payload = {"action": action, "target": target, "download_bytes": download_bytes, "source": source, "artifact_id": artifact_id}
        with self._transaction() as db:
            row = db.execute("SELECT * FROM workload_approvals WHERE id=?", (approval_id,)).fetchone()
            if row is None:
                raise PermissionError("approval not found")
            existing = db.execute("SELECT payload FROM workload_action_reservations WHERE approval_id=? AND action_id=?", (approval_id, action_id)).fetchone()
            if existing:
                if json.loads(existing["payload"]) != payload:
                    raise ValueError("action id already binds different contents")
                return {"action_id": action_id, "reserved": True, "replayed": True, "execute": False}
            if row["draft_revision"] != self._revision(db, "workload_drafts", row["draft_id"]):
                raise PermissionError("draft edited; previous approval is superseded")
            envelope = json.loads(row["envelope"])
            if not envelope["actions"].get(action, False) or target not in envelope["targets"]:
                raise PermissionError("action or target is outside the approved envelope")
            if time.time() - row["created_at"] >= envelope["limits"]["exploration_seconds"]:
                raise PermissionError("approved exploration time has expired")
            if action == "download":
                if envelope["network"] == "offline" or source not in envelope["sources"]:
                    raise PermissionError("download source is not authorized")
                if not isinstance(artifact_id, str) or not artifact_id:
                    raise ValueError("download requires an exact artifact identity")
                previous = [json.loads(r[0]) for r in db.execute("SELECT payload FROM workload_action_reservations WHERE approval_id=?", (approval_id,))]
                same_artifact = sum(p["download_bytes"] for p in previous if p.get("artifact_id") == artifact_id)
                total = sum(p["download_bytes"] for p in previous)
                if same_artifact + download_bytes > envelope["limits"]["per_artifact_bytes"] or total + download_bytes > envelope["limits"]["total_download_bytes"]:
                    raise PermissionError("download exceeds approved remaining budget")
                artifacts = {p["artifact_id"] for p in previous if p.get("artifact_id")} | {artifact_id}
                if len(artifacts) > envelope["limits"]["max_artifacts"]:
                    raise PermissionError("artifact search limit exhausted")
            db.execute("INSERT INTO workload_action_reservations VALUES(?,?,?,?)", (approval_id, action_id, canonical_json(payload), time.time()))
        return {"action_id": action_id, "reserved": True, "replayed": False, "execute": True}

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with self._transaction() as db:
            row = db.execute("SELECT * FROM workload_approvals WHERE id=?", (approval_id,)).fetchone()
            if row is None:
                raise KeyError(approval_id)
            draft = db.execute("SELECT * FROM workload_drafts WHERE id=? AND revision=?", (row["draft_id"], row["draft_revision"])).fetchone()
            if draft is None:
                raise KeyError(row["draft_id"])
        return {
            "approval_id": row["id"], "draft_id": row["draft_id"], "revision": row["draft_revision"],
            "contract_hash": row["contract_hash"], "policy_id": row["policy_id"],
            "policy_revision": row["policy_revision"], "envelope_hash": row["envelope_hash"],
            "envelope": json.loads(row["envelope"]), "contract": json.loads(draft["contract"]),
        }

    def create_run(self, *, draft_id: str, approval_id: str, payload: dict[str, Any] | None = None, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or uuid.uuid4().hex
        now = time.time()
        with self._transaction() as db:
            existing = db.execute("SELECT * FROM workload_runs WHERE id=?", (run_id,)).fetchone()
            if not existing:
                db.execute("INSERT INTO workload_runs VALUES(?,?,?,?,?,?,?)", (run_id, draft_id, approval_id, "QUEUED", canonical_json(_run_json_safe(payload or {})), now, now))
                db.execute("INSERT INTO workload_run_events VALUES(?,?,?,?,?,?)", (run_id, 1, "queued", "Workload run accepted", "{}", now))
            elif existing["draft_id"] != draft_id or existing["approval_id"] != approval_id:
                raise ValueError("run id is already bound to a different workload approval")
        return self.get_run(run_id)

    def update_run(self, run_id: str, *, status: str | None = None, payload: dict[str, Any] | None = None, stage: str | None = None, message: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.time()
        with self._transaction() as db:
            row = db.execute("SELECT * FROM workload_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            current_payload = json.loads(row["payload"])
            if payload:
                current_payload.update(payload)
            next_status = status or row["status"]
            db.execute("UPDATE workload_runs SET status=?, payload=?, updated_at=? WHERE id=?", (next_status, canonical_json(_run_json_safe(current_payload)), now, run_id))
            if stage or message:
                sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM workload_run_events WHERE run_id=?", (run_id,)).fetchone()[0]
                db.execute("INSERT INTO workload_run_events VALUES(?,?,?,?,?,?)", (run_id, sequence, stage or "update", message or next_status, canonical_json(details or {}), now))
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._transaction() as db:
            row = db.execute("SELECT * FROM workload_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            events = db.execute("SELECT sequence, stage, message, payload, created_at FROM workload_run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        return {"run_id": row["id"], "draft_id": row["draft_id"], "approval_id": row["approval_id"], "status": row["status"],
                "created_at": row["created_at"], "updated_at": row["updated_at"], "result": json.loads(row["payload"]),
                "events": [{"sequence": item["sequence"], "stage": item["stage"], "message": item["message"], "details": json.loads(item["payload"]), "created_at": item["created_at"]} for item in events]}

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._transaction() as db:
            rows = db.execute("SELECT id FROM workload_runs ORDER BY updated_at DESC LIMIT ?", (min(max(1, int(limit)), 500),)).fetchall()
        return [self.get_run(row["id"]) for row in rows]
