#!/usr/bin/env python3
"""Local E-project application server with a SQLite-backed JSON API."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date, datetime
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "eproject.sqlite3"
MAX_BODY_SIZE = 1_000_000
API_ENTITIES = {
    "projects": "projects",
    "people": "participants",
    "activities": "activities",
    "events": "calendar_events",
}
STATUSES = {
    "projects": {"Planejado", "Em andamento", "Pausado", "Encerrado"},
    "activities": {"Pendente", "Em andamento", "Concluída"},
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
        connection.executescript((ROOT / "database.sql").read_text(encoding="utf-8"))
        connection.execute("PRAGMA user_version = 1")


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


def record_id(payload: dict, *, imported: bool = False) -> str:
    value = payload.get("id")
    if imported and value is not None:
        if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
            raise ValueError("O identificador do registro é inválido.")
        return value
    return uuid.uuid4().hex


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
        optional_reference(connection, payload.get("projectId"), "projects", "projeto"),
    )


def activity_values(connection: sqlite3.Connection, payload: dict) -> tuple:
    status = clean_text(payload, "status") or "Pendente"
    if status not in STATUSES["activities"]:
        raise ValueError("A situação da atividade não é válida.")
    due_date = clean_optional_date(payload.get("dueDate"), "prazo")
    return (
        clean_text(payload, "title", required=True, limit=200),
        optional_reference(connection, payload.get("projectId"), "projects", "projeto"),
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
        optional_reference(connection, payload.get("projectId"), "projects", "projeto"),
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


def rows_for(connection: sqlite3.Connection, table: str) -> list[dict]:
    if table == "projects":
        rows = connection.execute("SELECT id, name, program, coordinator, unit, start_date AS start, end_date AS end, status, progress, description FROM projects ORDER BY name")
    elif table == "participants":
        rows = connection.execute("SELECT id, name, email, role, unit, project_id AS projectId FROM participants ORDER BY name")
    elif table == "activities":
        rows = connection.execute("SELECT id, title, project_id AS projectId, responsible_id AS responsibleId, due_date AS dueDate, status, type, description FROM activities ORDER BY due_date, title")
    else:
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


def bootstrap_data() -> dict:
    initialize_database()
    with connect() as connection:
        return {
            "projects": rows_for(connection, "projects"),
            "people": rows_for(connection, "participants"),
            "activities": rows_for(connection, "activities"),
            "events": rows_for(connection, "calendar_events"),
        }


def _create_record(
    connection: sqlite3.Connection,
    entity: str,
    payload: dict,
    *,
    imported: bool = False,
) -> str:
    identifier = record_id(payload, imported=imported)
    if entity == "projects":
        values = project_values(payload)
        connection.execute(
            """INSERT INTO projects
               (id, name, program, coordinator, unit, start_date, end_date, status, progress, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, *values),
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


def create_record(entity: str, payload: dict, *, imported: bool = False) -> str:
    with connect() as connection:
        return _create_record(connection, entity, payload, imported=imported)


def update_record(entity: str, identifier: str, payload: dict) -> None:
    table = API_ENTITIES[entity]
    with connect() as connection:
        if connection.execute(f"SELECT 1 FROM {table} WHERE id = ?", (identifier,)).fetchone() is None:
            raise LookupError("Registro não encontrado.")
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


def delete_record(entity: str, identifier: str) -> None:
    table = API_ENTITIES[entity]
    with connect() as connection:
        cursor = connection.execute(f"DELETE FROM {table} WHERE id = ?", (identifier,))
        if cursor.rowcount == 0:
            raise LookupError("Registro não encontrado.")


def import_initial_data(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("O conteúdo da importação é inválido.")
    initialize_database()
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        count = sum(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in API_ENTITIES.values())
        if count:
            raise RuntimeError("O banco já possui dados; a importação inicial foi recusada.")
        for entity in ("projects", "people", "activities", "events"):
            records = payload.get(entity, [])
            if not isinstance(records, list) or len(records) > 10000:
                raise ValueError(f"A lista de '{entity}' é inválida.")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError(f"Há um registro inválido em '{entity}'.")
                _create_record(connection, entity, record, imported=True)


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
                self.send_json(200, bootstrap_data())
                return True
            if path == "/api/backup" and self.command == "GET":
                initialize_database()
                with connect() as connection:
                    self.send_download(connection.serialize(), "application/vnd.sqlite3", "eproject-backup.sqlite3")
                return True
            if path == "/api/events" and self.command == "GET":
                query = parse_qs(parsed.query)
                events = bootstrap_data()["events"]
                if query.get("from") and query.get("to"):
                    start, end = query["from"][0], query["to"][0]
                    events = [event for event in events if start <= event["startAt"][:10] <= end]
                self.send_json(200, {"events": events})
                return True
            if path == "/api/import" and self.command == "POST":
                import_initial_data(self.read_json())
                self.send_json(201, {"message": "Dados iniciais importados."})
                return True

            parts = path.strip("/").split("/")
            entity = parts[1] if len(parts) >= 2 else ""
            if entity not in API_ENTITIES:
                self.send_json(404, {"error": "Endpoint não encontrado."})
                return True
            if len(parts) == 2 and self.command == "POST":
                identifier = create_record(entity, self.read_json())
                self.send_json(201, {"id": identifier})
                return True
            if len(parts) == 3 and self.command == "PUT":
                identifier = parts[2]
                if not ID_PATTERN.fullmatch(identifier):
                    raise ValueError("O identificador do registro é inválido.")
                update_record(entity, identifier, self.read_json())
                self.send_json(200, {"id": identifier})
                return True
            if len(parts) == 3 and self.command == "DELETE":
                identifier = parts[2]
                if not ID_PATTERN.fullmatch(identifier):
                    raise ValueError("O identificador do registro é inválido.")
                delete_record(entity, identifier)
                self.send_json(200, {"id": identifier})
                return True
            self.send_json(405, {"error": "Método não permitido para este endpoint."})
        except LookupError as exc:
            self.send_json(404, {"error": str(exc)})
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
