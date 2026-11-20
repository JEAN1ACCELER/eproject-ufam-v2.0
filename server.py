#!/usr/bin/env python3
"""Local E-project application server with a SQLite-backed JSON API."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
import hashlib
import secrets
import hmac
from datetime import date, datetime
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("EPROJECT_DATABASE", str(ROOT / "data" / "eproject-ufam.sqlite3"))).expanduser()
MAX_BODY_SIZE = 1_000_000
API_ENTITIES = {
    "projects": "projects",
    "people": "participants",
    "activities": "activities",
    "tasks": "activities",
    "events": "calendar_events",
    "edital": "edital",
    "documents": "project_documents",
    "attendance": "meeting_attendance",
    "notifications": "notifications",
}
SESSIONS: dict[str, dict] = {}
STATUSES = {
    "projects": {"Planejado", "Em andamento", "Concluído", "Suspenso", "Cancelado", "Pausado", "Encerrado"},
    "activities": {"Pendente", "Em andamento", "Concluída", "Cancelada"},
    "events": {"Agendado", "Realizado", "Cancelado"},
}
ROLES = {"Professor(a)", "Aluno(a)", "Voluntário(a)"}
EVENT_REMINDERS = {0, 10, 30, 60, 1440}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript((ROOT / "database.sql").read_text(encoding="utf-8"))
        project_columns = {row["name"] for row in connection.execute("PRAGMA table_info(projects)")}
        if "owner_id" not in project_columns:
            connection.execute("ALTER TABLE projects ADD COLUMN owner_id TEXT REFERENCES users(id) ON DELETE SET NULL")
        project_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'projects'"
        ).fetchone()["sql"]
        if not all(status in project_schema for status in ("Concluído", "Suspenso", "Cancelado")):
            connection.execute(
                """CREATE TABLE projects_new (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
                    program TEXT NOT NULL CHECK (length(program) BETWEEN 1 AND 60),
                    coordinator TEXT NOT NULL DEFAULT '',
                    unit TEXT NOT NULL DEFAULT '',
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT NOT NULL DEFAULT 'Planejado'
                        CHECK (status IN ('Planejado', 'Em andamento', 'Concluído', 'Suspenso', 'Cancelado', 'Pausado', 'Encerrado')),
                    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
                    description TEXT NOT NULL DEFAULT '',
                    owner_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date)
                )"""
            )
            connection.execute(
                """INSERT INTO projects_new
                   (id, name, program, coordinator, unit, start_date, end_date, status, progress, description, owner_id, created_at, updated_at)
                   SELECT id, name, program, coordinator, unit, start_date, end_date, status, progress, description, owner_id, created_at, updated_at
                   FROM projects"""
            )
            connection.execute("DROP TABLE projects")
            connection.execute("ALTER TABLE projects_new RENAME TO projects")
        activity_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'activities'"
        ).fetchone()["sql"]
        if "project_id TEXT NOT NULL" not in activity_schema or "Cancelada" not in activity_schema:
            orphan_count = connection.execute("SELECT COUNT(*) FROM activities WHERE project_id IS NULL").fetchone()[0]
            if orphan_count:
                legacy_project_id = f"legacy-{uuid.uuid4().hex}"
                connection.execute(
                    "INSERT INTO projects (id, name, program, status, progress, description) VALUES (?, ?, ?, ?, 0, ?)",
                    (legacy_project_id, "Tarefas sem projeto (dados legados)", "Legado", "Planejado", "Projeto criado para preservar tarefas antigas sem vínculo."),
                )
                connection.execute("UPDATE activities SET project_id = ? WHERE project_id IS NULL", (legacy_project_id,))
            connection.execute("DROP TRIGGER IF EXISTS activities_require_project_insert")
            connection.execute("DROP TRIGGER IF EXISTS activities_require_project_update")
            connection.execute("DROP INDEX IF EXISTS idx_activities_due_date")
            connection.execute("DROP INDEX IF EXISTS idx_activities_project")
            connection.execute(
                """CREATE TABLE activities_new (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    responsible_id TEXT REFERENCES participants(id) ON DELETE SET NULL,
                    due_date TEXT,
                    status TEXT NOT NULL DEFAULT 'Pendente'
                        CHECK (status IN ('Pendente', 'Em andamento', 'Concluída', 'Cancelada')),
                    type TEXT NOT NULL DEFAULT 'Outro',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            connection.execute(
                """INSERT INTO activities_new
                   (id, title, project_id, responsible_id, due_date, status, type, description, created_at, updated_at)
                   SELECT id, title, project_id, responsible_id, due_date, status, type, description, created_at, updated_at
                   FROM activities"""
            )
            connection.execute("DROP TABLE activities")
            connection.execute("ALTER TABLE activities_new RENAME TO activities")
            connection.execute("CREATE INDEX idx_activities_due_date ON activities(due_date)")
            connection.execute("CREATE INDEX idx_activities_project ON activities(project_id)")
        connection.execute(
            "UPDATE users SET active = 0 WHERE (id, email) IN ((?, ?), (?, ?), (?, ?), (?, ?))",
            ("u-admin", "admin@eproject.invalid", "u-orientador", "orientador@eproject.invalid",
             "u-orientando", "orientando@eproject.invalid", "u-coordenador", "coordenador@eproject.invalid"),
        )
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA user_version = 3")


def clean_text(payload: dict, key: str, *, required: bool = False, limit: int = 5000) -> str:
    value = payload.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"O campo '{key}' precisa ser texto.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Preencha o campo '{key}'.")
    if len(value) > limit:
        raise ValueError(f"O campo '{key}' ultrapassa o limite de {limit} caracteres.")
    return value


def clean_optional_date(value: object, key: str) -> str | None:
    if value in ("", None):
        return None
    if not isinstance(value, str):
        raise ValueError(f"A data '{key}' é inválida.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"Informe uma data válida para '{key}'.") from exc


def clean_datetime(value: object, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Preencha a data e o horário de '{key}'.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat(timespec="minutes")
    except ValueError as exc:
        raise ValueError(f"Informe uma data e horário válidos para '{key}'.") from exc


def optional_reference(connection: sqlite3.Connection, value: object, table: str, key: str) -> str | None:
    if value in ("", None):
        return None
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError(f"A referência de '{key}' é inválida.")
    if connection.execute(f"SELECT 1 FROM {table} WHERE id = ?", (value,)).fetchone() is None:
        raise ValueError(f"O registro selecionado em '{key}' não existe.")
    return value


def required_reference(connection: sqlite3.Connection, value: object, table: str, key: str) -> str:
    reference = optional_reference(connection, value, table, key)
    if reference is None:
        raise ValueError(f"Selecione um registro válido em '{key}'.")
    return reference


def require_project_access(connection: sqlite3.Connection, project_id: str, user: dict) -> None:
    project = connection.execute("SELECT owner_id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise LookupError("Projeto não encontrado.")
    if project["owner_id"] != user["id"]:
        raise PermissionError("Você não possui autorização para acessar este projeto.")


def record_id(payload: dict, *, imported: bool = False) -> str:
    value = payload.get("id")
    if imported and value is not None:
        if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
            raise ValueError("O identificador do registro é inválido.")
        return value
    return uuid.uuid4().hex


ITERATIONS = 210000


def password_credential(password: str) -> tuple[str, str, int]:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    if len(password) > 128:
        raise ValueError("A senha ultrapassa o limite de 128 caracteres.")
    salt = secrets.token_hex(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"), n=2**14, r=8, p=1, dklen=32)
    return salt, derived.hex(), ITERATIONS


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    if not isinstance(password, str):
        return False
    try:
        derived = hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(derived.hex(), password_hash)
    except (ValueError, TypeError):
        return False


def bearer_user(handler: "EProjectHandler") -> dict | None:
    authorization = handler.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    session = SESSIONS.get(authorization[7:].strip())
    return session


class AuthenticationError(PermissionError):
    pass


def require_user(handler: "EProjectHandler") -> dict:
    user = bearer_user(handler)
    if user is None:
        raise AuthenticationError("Autenticação necessária.")
    return user


def require_role(handler: "EProjectHandler", allowed: set[str]) -> dict:
    user = require_user(handler)
    if user["role"] not in allowed:
        raise PermissionError("Você não possui autorização para esta operação.")
    return user


def project_values(payload: dict) -> tuple:
    start = clean_optional_date(payload.get("start"), "início")
    end = clean_optional_date(payload.get("end"), "término")
    if start and end and start > end:
        raise ValueError("A data de término precisa ser igual ou posterior à data de início.")
    progress = payload.get("progress", 0)
    if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not float(progress).is_integer():
        raise ValueError("O progresso precisa ser um número de 0 a 100.")
    progress = int(progress)
    if not 0 <= progress <= 100:
        raise ValueError("O progresso precisa estar entre 0 e 100.")
    status = clean_text(payload, "status") or "Planejado"
    if status not in STATUSES["projects"]:
        raise ValueError("A situação do projeto não é válida.")
    return (
        clean_text(payload, "name", required=True, limit=200),
        clean_text(payload, "program", required=True, limit=60),
        clean_text(payload, "coordinator", limit=120),
        clean_text(payload, "unit", limit=160),
        start,
        end,
        status,
        progress,
        clean_text(payload, "description", limit=5000),
    )
def participant_values(connection: sqlite3.Connection, payload: dict) -> tuple:
    role = clean_text(payload, "role", required=True, limit=30)
    if role not in ROLES:
        raise ValueError("Selecione um perfil válido para o participante.")
    email = clean_text(payload, "email", required=True, limit=254)
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("Informe um e-mail válido.")
    return (
        clean_text(payload, "name", required=True, limit=120),
        email,
        role,
        clean_text(payload, "unit", limit=160),
        required_reference(connection, payload.get("projectId"), "projects", "projeto"),
    )


def activity_values(connection: sqlite3.Connection, payload: dict) -> tuple:
    status = clean_text(payload, "status") or "Pendente"
    if status not in STATUSES["activities"]:
        raise ValueError("A situação da atividade não é válida.")
    due_date = clean_optional_date(payload.get("dueDate"), "prazo")
    return (
        clean_text(payload, "title", required=True, limit=200),
        required_reference(connection, payload.get("projectId"), "projects", "projeto"),
        optional_reference(connection, payload.get("responsibleId"), "participants", "responsável"),
        due_date,
        status,
        clean_text(payload, "type") or "Outro",
        clean_text(payload, "description", limit=5000),
    )


def event_values(connection: sqlite3.Connection, payload: dict) -> tuple:
    start_at = clean_datetime(payload.get("startAt"), "início")
    end_at = clean_datetime(payload.get("endAt"), "término")
    start = datetime.fromisoformat(start_at)
    end = datetime.fromisoformat(end_at)
    if (start.tzinfo is None) != (end.tzinfo is None):
        raise ValueError("Início e término precisam usar o mesmo fuso horário.")
    if end <= start:
        raise ValueError("O horário de término precisa ser posterior ao início.")
    status = clean_text(payload, "status") or "Agendado"
    if status not in STATUSES["events"]:
        raise ValueError("A situação do evento não é válida.")
    reminder = payload.get("reminderMinutes", 0)
    if isinstance(reminder, bool) or not isinstance(reminder, int) or reminder not in EVENT_REMINDERS:
        raise ValueError("Selecione um intervalo válido para o lembrete.")
    participants = payload.get("participantIds", [])
    if not isinstance(participants, list) or len(participants) > 100:
        raise ValueError("A lista de participantes do evento é inválida.")
    participant_ids = list(dict.fromkeys(participants))
    for participant_id in participant_ids:
        optional_reference(connection, participant_id, "participants", "participante")
    return (
        clean_text(payload, "title", required=True, limit=200),
        required_reference(connection, payload.get("projectId"), "projects", "projeto"),
        optional_reference(connection, payload.get("activityId"), "activities", "atividade"),
        optional_reference(connection, payload.get("responsibleId"), "participants", "responsável"),
        clean_text(payload, "type") or "Reunião",
        start_at,
        end_at,
        clean_text(payload, "location", limit=240),
        status,
        reminder,
        clean_text(payload, "description", limit=5000),
        participant_ids,
    )


def rows_for(connection: sqlite3.Connection, table: str, *, owner_id: str | None = None) -> list[dict]:
    if table == "projects":
        rows = connection.execute(
            "SELECT id, name, program, coordinator, unit, start_date AS start, end_date AS end, status, progress, description FROM projects WHERE owner_id = ? ORDER BY name",
            (owner_id,),
        ) if owner_id is not None else connection.execute(
            "SELECT id, name, program, coordinator, unit, start_date AS start, end_date AS end, status, progress, description FROM projects ORDER BY name"
        )
    elif table == "participants":
        rows = connection.execute("SELECT id, name, email, role, unit, project_id AS projectId FROM participants ORDER BY name")
    elif table == "activities":
        rows = connection.execute("SELECT id, title, project_id AS projectId, responsible_id AS responsibleId, due_date AS dueDate, status, type, description FROM activities ORDER BY due_date, title")
    elif table == "edital":
        rows = connection.execute("SELECT id, title, source, pro_reitoria AS proReitoria, area, publication_date AS publicationDate, deadline, status, url, description FROM edital ORDER BY deadline, title")
    elif table == "project_documents":
        rows = connection.execute("SELECT id, project_id AS projectId, title, file_name AS fileName, file_type AS fileType, file_size AS fileSize, content, owner_id AS ownerId FROM project_documents ORDER BY title")
    elif table == "meeting_attendance":
        rows = connection.execute("SELECT id, event_id AS eventId, participant_id AS participantId, checked_in_at AS checkedInAt, location FROM meeting_attendance ORDER BY checked_in_at")
    elif table == "notifications":
        rows = connection.execute("SELECT id, user_id AS userId, title, message, category, read FROM notifications ORDER BY created_at DESC")
    elif table == "users":
        rows = connection.execute("SELECT id, name, email, cpf, cns, role, accepted_terms AS acceptedTerms, accepted_privacy AS acceptedPrivacy, active FROM users ORDER BY name")
    elif table == "calendar_events":
        rows = connection.execute(
            """SELECT e.id, e.title, e.project_id AS projectId, e.activity_id AS activityId,
                      e.responsible_id AS responsibleId, e.event_type AS type, e.start_at AS startAt,
                      e.end_at AS endAt, e.location, e.status, e.reminder_minutes AS reminderMinutes,
                      e.description
               FROM calendar_events AS e ORDER BY e.start_at"""
        )
    results = [dict(row) for row in rows]
    if table == "calendar_events":
        for item in results:
            participants = connection.execute(
                "SELECT participant_id FROM calendar_event_participants WHERE event_id = ? ORDER BY participant_id",
                (item["id"],),
            )
            item["participantIds"] = [row["participant_id"] for row in participants]
    return results


def bootstrap_data(user: dict) -> dict:
    initialize_database()
    with connect() as connection:
        projects = rows_for(connection, "projects", owner_id=user["id"])
        project_ids = {project["id"] for project in projects}
        people = [person for person in rows_for(connection, "participants") if person["projectId"] in project_ids]
        activities = [activity for activity in rows_for(connection, "activities") if activity["projectId"] in project_ids]
        events = [event for event in rows_for(connection, "calendar_events") if event["projectId"] in project_ids]
        event_ids = {event["id"] for event in events}
        return {
            "projects": projects,
            "people": people,
            "activities": activities,
            "tasks": activities,
            "events": events,
            "edital": rows_for(connection, "edital"),
            "documents": [item for item in rows_for(connection, "project_documents") if item["projectId"] in project_ids],
            "attendance": [item for item in rows_for(connection, "meeting_attendance") if item["eventId"] in event_ids],
            "notifications": [item for item in rows_for(connection, "notifications") if item["userId"] in (None, user["id"])],
        }


def _create_record(
    connection: sqlite3.Connection,
    entity: str,
    payload: dict,
    *,
    imported: bool = False,
    user_id: str | None = None,
) -> str:
    identifier = record_id(payload, imported=imported)
    if entity == "projects":
        values = project_values(payload)
        connection.execute(
            """INSERT INTO projects
                    (id, name, program, coordinator, unit, start_date, end_date, status, progress, description, owner_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (identifier, *values, user_id),
        )
    elif entity == "people":
        values = participant_values(connection, payload)
        connection.execute(
            "INSERT INTO participants (id, name, email, role, unit, project_id) VALUES (?, ?, ?, ?, ?, ?)",
            (identifier, *values),
        )
    elif entity == "activities":
        values = activity_values(connection, payload)
        connection.execute(
            """INSERT INTO activities
               (id, title, project_id, responsible_id, due_date, status, type, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, *values),
        )
    else:
        values = event_values(connection, payload)
        connection.execute(
            """INSERT INTO calendar_events
               (id, title, project_id, activity_id, responsible_id, event_type, start_at, end_at,
                location, status, reminder_minutes, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, *values[:11]),
        )
        connection.executemany(
            "INSERT INTO calendar_event_participants (event_id, participant_id) VALUES (?, ?)",
            [(identifier, participant_id) for participant_id in values[11]],
        )
    return identifier


def canonical_entity(entity: str) -> str:
    return "activities" if entity == "tasks" else entity


def create_record(entity: str, payload: dict, user: dict, *, imported: bool = False) -> str:
    entity = canonical_entity(entity)
    with connect() as connection:
        if entity != "projects":
            project_id = required_reference(connection, payload.get("projectId"), "projects", "projeto")
            require_project_access(connection, project_id, user)
        return _create_record(connection, entity, payload, imported=imported, user_id=user["id"])


def update_record(entity: str, identifier: str, payload: dict, user: dict) -> None:
    entity = canonical_entity(entity)
    table = API_ENTITIES[entity]
    with connect() as connection:
        current = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (identifier,)).fetchone()
        if current is None:
            raise LookupError("Registro não encontrado.")
        if entity == "projects":
            require_project_access(connection, identifier, user)
        else:
            require_project_access(connection, current["project_id"], user)
            project_id = required_reference(connection, payload.get("projectId"), "projects", "projeto")
            require_project_access(connection, project_id, user)
        if entity == "projects":
            values = project_values(payload)
            connection.execute(
                """UPDATE projects SET name=?, program=?, coordinator=?, unit=?, start_date=?, end_date=?,
                   status=?, progress=?, description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (*values, identifier),
            )
        elif entity == "people":
            values = participant_values(connection, payload)
            connection.execute(
                """UPDATE participants SET name=?, email=?, role=?, unit=?, project_id=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (*values, identifier),
            )
        elif entity == "activities":
            values = activity_values(connection, payload)
            connection.execute(
                """UPDATE activities SET title=?, project_id=?, responsible_id=?, due_date=?,
                   status=?, type=?, description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (*values, identifier),
            )
        else:
            values = event_values(connection, payload)
            connection.execute(
                """UPDATE calendar_events SET title=?, project_id=?, activity_id=?, responsible_id=?,
                   event_type=?, start_at=?, end_at=?, location=?, status=?, reminder_minutes=?,
                   description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (*values[:11], identifier),
            )
            connection.execute("DELETE FROM calendar_event_participants WHERE event_id = ?", (identifier,))
            connection.executemany(
                "INSERT INTO calendar_event_participants (event_id, participant_id) VALUES (?, ?)",
                [(identifier, participant_id) for participant_id in values[11]],
            )


def delete_record(entity: str, identifier: str, user: dict) -> None:
    entity = canonical_entity(entity)
    table = API_ENTITIES[entity]
    with connect() as connection:
        if entity == "projects":
            require_project_access(connection, identifier, user)
            connection.execute("DELETE FROM activities WHERE project_id = ?", (identifier,))
        else:
            row = connection.execute(f"SELECT project_id FROM {table} WHERE id = ?", (identifier,)).fetchone()
            if row is None:
                raise LookupError("Registro não encontrado.")
            require_project_access(connection, row["project_id"], user)
        cursor = connection.execute(f"DELETE FROM {table} WHERE id = ?", (identifier,))
        if cursor.rowcount == 0:
            raise LookupError("Registro não encontrado.")


def import_initial_data(payload: dict, user: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("O conteúdo da importação é inválido.")
    initialize_database()
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        count = sum(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in set(API_ENTITIES.values()))
        if count:
            raise RuntimeError("O banco já possui dados; a importação inicial foi recusada.")
        for entity in ("projects", "people", "activities", "events"):
            records = payload.get(entity, [])
            if not isinstance(records, list) or len(records) > 10000:
                raise ValueError(f"A lista de '{entity}' é inválida.")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError(f"Há um registro inválido em '{entity}'.")
                if entity != "projects":
                    project_id = required_reference(connection, record.get("projectId"), "projects", "projeto")
                    require_project_access(connection, project_id, user)
                _create_record(connection, entity, record, imported=True, user_id=user["id"])


class EProjectHandler(SimpleHTTPRequestHandler):
    server_version = "E-project/1.0"
    STATIC_FILES = {"index.html", "styles.css", "app.js"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("O tamanho da solicitação é inválido.") from exc
        if length < 1 or length > MAX_BODY_SIZE:
            raise ValueError("O conteúdo enviado está vazio ou ultrapassa 1 MB.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("O conteúdo enviado não é um JSON válido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("O conteúdo enviado precisa ser um objeto JSON.")
        return payload

    def api_request(self) -> bool:
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            return False
        try:
            if path == "/api/bootstrap" and self.command == "GET":
                user = require_user(self)
                self.send_json(200, bootstrap_data(user))
                return True
            if path == "/api/backup" and self.command == "GET":
                require_role(self, {"ADMINISTRADOR"})
                initialize_database()
                with connect() as connection:
                    self.send_download(connection.serialize(), "application/vnd.sqlite3", "eproject-backup.sqlite3")
                return True
            if path == "/api/events" and self.command == "GET":
                user = require_user(self)
                query = parse_qs(parsed.query)
                events = bootstrap_data(user)["events"]
                if query.get("from") and query.get("to"):
                    start, end = query["from"][0], query["to"][0]
                    events = [event for event in events if start <= event["startAt"][:10] <= end]
                self.send_json(200, {"events": events})
                return True
            if path == "/api/import" and self.command == "POST":
                user = require_role(self, {"ORIENTADOR", "ADMINISTRADOR"})
                import_initial_data(self.read_json(), user)
                self.send_json(201, {"message": "Dados iniciais importados."})
                return True
            if path == "/api/register" and self.command == "POST":
                payload = self.read_json()
                name = clean_text(payload, "name", required=True, limit=120)
                email = clean_text(payload, "email", required=True, limit=254).lower()
                cpf = clean_text(payload, "cpf", limit=14) or None
                cns = clean_text(payload, "cns", limit=20) or None
                password = payload.get("password")
                accepted_terms = payload.get("acceptedTerms") is True
                accepted_privacy = payload.get("acceptedPrivacy") is True
                if "@" not in email or email.startswith("@") or email.endswith("@"):
                    raise ValueError("Informe um e-mail válido.")
                if not accepted_terms or not accepted_privacy:
                    raise ValueError("É necessário aceitar os termos e a política de privacidade.")
                try:
                    with connect() as connection:
                        account_count = connection.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0]
                        role = "ORIENTADOR" if account_count == 0 else "ORIENTANDO"
                        identifier = uuid.uuid4().hex
                        salt, password_hash, iterations = password_credential(password)
                        connection.execute(
                            "INSERT INTO users (id, name, email, cpf, cns, role, accepted_terms, accepted_privacy) VALUES (?, ?, ?, ?, ?, ?, 1, 1)",
                            (identifier, name, email, cpf, cns, role),
                        )
                        connection.execute(
                            "INSERT INTO password_credentials (user_id, password_salt, password_hash, iterations) VALUES (?, ?, ?, ?)",
                            (identifier, salt, password_hash, iterations),
                        )
                        if account_count == 0:
                            connection.execute("UPDATE projects SET owner_id = ? WHERE owner_id IS NULL", (identifier,))
                except sqlite3.IntegrityError as exc:
                    raise RuntimeError("Não foi possível concluir o cadastro. Confira os dados informados.") from exc
                self.send_json(201, {"id": identifier, "message": "Cadastro realizado com sucesso."})
                return True
            if path == "/api/login" and self.command == "POST":
                payload = self.read_json()
                email = clean_text(payload, "email", required=True, limit=254).lower()
                password = payload.get("password")
                with connect() as connection:
                    user = connection.execute(
                        "SELECT u.id, u.name, u.email, u.role, u.active, p.password_salt, p.password_hash FROM users u JOIN password_credentials p ON p.user_id = u.id WHERE u.email = ?",
                        (email,),
                    ).fetchone()
                if user is None or not user["active"] or not verify_password(password if isinstance(password, str) else "", user["password_salt"], user["password_hash"]):
                    raise AuthenticationError("E-mail ou senha inválidos.")
                token = secrets.token_urlsafe(32)
                session = {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}
                SESSIONS[token] = session
                self.send_json(200, {"token": token, "user": session})
                return True
            if path == "/api/logout" and self.command == "POST":
                authorization = self.headers.get("Authorization", "")
                if authorization.startswith("Bearer "):
                    SESSIONS.pop(authorization[7:].strip(), None)
                self.send_json(200, {"message": "Sessão encerrada."})
                return True
            if path == "/api/session" and self.command == "GET":
                self.send_json(200, {"user": require_user(self)})
                return True
            if path == "/api/users" and self.command == "GET":
                require_role(self, {"ADMINISTRADOR", "COORDENADOR"})
                with connect() as connection:
                    users = [dict(row) for row in connection.execute(
                        "SELECT id, name, email, cpf, cns, role, active FROM users ORDER BY name"
                    )]
                self.send_json(200, {"users": users})
                return True
            if path in {"/api/editais", "/api/documents", "/api/attendance", "/api/notifications"}:
                kind = path.rsplit("/", 1)[1]
                user = require_user(self)
                if kind == "editais" and self.command in {"POST", "PUT", "DELETE"}:
                    require_role(self, {"ADMINISTRADOR", "COORDENADOR"})
                table = {"editais": "edital", "documents": "project_documents", "attendance": "meeting_attendance", "notifications": "notifications"}[kind]
                if self.command == "GET":
                    data_key = {"editais": "edital", "documents": "documents", "attendance": "attendance", "notifications": "notifications"}[kind]
                    self.send_json(200, {kind: bootstrap_data(user)[data_key]})
                    return True
                if self.command == "POST":
                    payload = self.read_json()
                    identifier = uuid.uuid4().hex
                    with connect() as connection:
                        if kind == "editais":
                            connection.execute(
                                "INSERT INTO edital (id,title,source,pro_reitoria,area,publication_date,deadline,status,url,description) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (identifier, clean_text(payload, "title", required=True, limit=200),
                                 clean_text(payload, "source", limit=120), clean_text(payload, "proReitoria", limit=120),
                                 clean_text(payload, "area", limit=120), clean_optional_date(payload.get("publicationDate"), "publicação"),
                                 clean_optional_date(payload.get("deadline"), "prazo"), clean_text(payload, "status") or "Aberto",
                                 clean_text(payload, "url", limit=500), clean_text(payload, "description", limit=5000)),
                            )
                        elif kind == "documents":
                            project_id = required_reference(connection, payload.get("projectId"), "projects", "projeto")
                            require_project_access(connection, project_id, user)
                            connection.execute(
                                "INSERT INTO project_documents (id,project_id,title,file_name,file_type,file_size,content,owner_id) VALUES (?,?,?,?,?,?,?,?)",
                                (identifier, project_id, clean_text(payload, "title", required=True, limit=200),
                                 clean_text(payload, "fileName", limit=255), clean_text(payload, "fileType", limit=120),
                                 max(0, int(payload.get("fileSize", 0))), clean_text(payload, "content", limit=10000),
                                 require_user(self)["id"]),
                            )
                        elif kind == "attendance":
                            event_id = required_reference(connection, payload.get("eventId"), "calendar_events", "reunião")
                            participant_id = required_reference(connection, payload.get("participantId"), "participants", "participante")
                            event_project = connection.execute("SELECT project_id FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
                            person_project = connection.execute("SELECT project_id FROM participants WHERE id = ?", (participant_id,)).fetchone()
                            require_project_access(connection, event_project["project_id"], user)
                            if person_project["project_id"] != event_project["project_id"]:
                                raise ValueError("O participante não pertence ao projeto da reunião.")
                            connection.execute(
                                "INSERT INTO meeting_attendance (id,event_id,participant_id,checked_in_at,location) VALUES (?,?,?,?,?)",
                                (identifier, event_id, participant_id, clean_datetime(payload.get("checkedInAt"), "check-in"),
                                 clean_text(payload, "location", limit=240)),
                            )
                        else:
                            connection.execute(
                                "INSERT INTO notifications (id,user_id,title,message,category) VALUES (?,?,?,?,?)",
                                (identifier, user["id"], clean_text(payload, "title", required=True, limit=200),
                                 clean_text(payload, "message", required=True, limit=1000),
                                 clean_text(payload, "category") or "Sistema"),
                            )
                    self.send_json(201, {"id": identifier})
                    return True
            custom_match = re.match(r"^/api/(editais|documents|attendance|notifications)/([A-Za-z0-9_-]{1,80})$", path)
            if custom_match:
                kind, identifier = custom_match.groups()
                user = require_user(self)
                if kind == "editais":
                    require_role(self, {"ADMINISTRADOR", "COORDENADOR"})
                table = {"editais": "edital", "documents": "project_documents", "attendance": "meeting_attendance", "notifications": "notifications"}[kind]
                if self.command == "DELETE":
                    with connect() as connection:
                        if kind == "documents":
                            record = connection.execute("SELECT project_id FROM project_documents WHERE id = ?", (identifier,)).fetchone()
                            if record is None:
                                raise LookupError("Registro não encontrado.")
                            require_project_access(connection, record["project_id"], user)
                        elif kind == "attendance":
                            record = connection.execute("SELECT e.project_id FROM meeting_attendance AS a JOIN calendar_events AS e ON e.id = a.event_id WHERE a.id = ?", (identifier,)).fetchone()
                            if record is None:
                                raise LookupError("Registro não encontrado.")
                            require_project_access(connection, record["project_id"], user)
                        elif kind == "notifications":
                            record = connection.execute("SELECT user_id FROM notifications WHERE id = ?", (identifier,)).fetchone()
                            if record is None:
                                raise LookupError("Registro não encontrado.")
                            if record["user_id"] != user["id"]:
                                raise PermissionError("Você não pode alterar esta notificação.")
                        cursor = connection.execute(f"DELETE FROM {table} WHERE id = ?", (identifier,))
                        if cursor.rowcount == 0:
                            raise LookupError("Registro não encontrado.")
                    self.send_json(200, {"id": identifier})
                    return True
                if self.command == "PUT":
                    payload = self.read_json()
                    with connect() as connection:
                        if kind == "editais":
                            connection.execute(
                                "UPDATE edital SET title=?,source=?,pro_reitoria=?,area=?,publication_date=?,deadline=?,status=?,url=?,description=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                (clean_text(payload, "title", required=True, limit=200),
                                 clean_text(payload, "source", limit=120), clean_text(payload, "proReitoria", limit=120),
                                 clean_text(payload, "area", limit=120), clean_optional_date(payload.get("publicationDate"), "publicação"),
                                 clean_optional_date(payload.get("deadline"), "prazo"), clean_text(payload, "status") or "Aberto",
                                 clean_text(payload, "url", limit=500), clean_text(payload, "description", limit=5000), identifier),
                            )
                        elif kind == "notifications":
                            record = connection.execute("SELECT user_id FROM notifications WHERE id = ?", (identifier,)).fetchone()
                            if record is None:
                                raise LookupError("Registro não encontrado.")
                            if record["user_id"] != user["id"]:
                                raise PermissionError("Você não pode alterar esta notificação.")
                            connection.execute(
                                "UPDATE notifications SET read=? WHERE id=?",
                                (1 if payload.get("read") else 0, identifier),
                            )
                        else:
                            raise LookupError("A atualização deste tipo não está disponível.")
                    self.send_json(200, {"id": identifier})
                    return True

            parts = path.strip("/").split("/")
            entity = parts[1] if len(parts) >= 2 else ""
            if entity not in API_ENTITIES:
                self.send_json(404, {"error": "Endpoint não encontrado."})
                return True
            if len(parts) == 2 and self.command == "POST":
                user = require_user(self)
                if entity == "projects":
                    require_role(self, {"ORIENTADOR", "COORDENADOR", "ADMINISTRADOR"})
                identifier = create_record(entity, self.read_json(), user)
                self.send_json(201, {"id": identifier})
                return True
            if len(parts) == 3 and self.command == "PUT":
                user = require_user(self)
                if entity == "projects":
                    require_role(self, {"ORIENTADOR", "COORDENADOR", "ADMINISTRADOR"})
                identifier = parts[2]
                if not ID_PATTERN.fullmatch(identifier):
                    raise ValueError("O identificador do registro é inválido.")
                update_record(entity, identifier, self.read_json(), user)
                self.send_json(200, {"id": identifier})
                return True
            if len(parts) == 3 and self.command == "DELETE":
                user = require_user(self)
                if entity == "projects":
                    require_role(self, {"ORIENTADOR", "COORDENADOR", "ADMINISTRADOR"})
                identifier = parts[2]
                if not ID_PATTERN.fullmatch(identifier):
                    raise ValueError("O identificador do registro é inválido.")
                delete_record(entity, identifier, user)
                self.send_json(200, {"id": identifier})
                return True
            self.send_json(405, {"error": "Método não permitido para este endpoint."})
        except LookupError as exc:
            self.send_json(404, {"error": str(exc)})
        except AuthenticationError as exc:
            self.send_json(401, {"error": str(exc)})
        except PermissionError as exc:
            self.send_json(403, {"error": str(exc)})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self.send_json(409, {"error": str(exc)})
        except sqlite3.IntegrityError as exc:
            self.send_json(409, {"error": f"A operação viola uma regra do banco de dados: {exc}."})
        except sqlite3.Error as exc:
            self.log_error("Erro de banco de dados: %s", exc)
            self.send_json(500, {"error": "Não foi possível concluir a operação no banco de dados."})
        return True

    def do_GET(self) -> None:
        if self.api_request():
            return
        path = urlparse(self.path).path
        if path not in {"/", *(f"/{name}" for name in self.STATIC_FILES)}:
            self.send_json(404, {"error": "Arquivo não encontrado."})
            return
        super().do_GET()

    def send_download(self, content: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if not self.api_request():
            self.send_json(404, {"error": "Endpoint não encontrado."})

    def do_PUT(self) -> None:
        if not self.api_request():
            self.send_json(404, {"error": "Endpoint não encontrado."})

    def do_DELETE(self) -> None:
        if not self.api_request():
            self.send_json(404, {"error": "Endpoint não encontrado."})

    def log_message(self, format_string: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")


def main() -> None:
    initialize_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), EProjectHandler)
    print("E-project disponível em http://127.0.0.1:8000 (somente neste computador).")
    print(f"Banco de dados: {DATABASE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
