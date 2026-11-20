import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class ApplicationApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.previous_database = server.DATABASE
        server.DATABASE = Path(self.temporary_directory.name) / "eproject.sqlite3"
        server.initialize_database()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.EProjectHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.token = ""
        status, user = self.request("POST", "/api/register", {
            "name": "Orientador de Teste",
            "email": "orientador@example.invalid",
            "password": "SenhaSegura123!",
            "acceptedTerms": True,
            "acceptedPrivacy": True,
        })
        self.assertEqual(status, 201)
        self.user_id = user["id"]
        self.login("orientador@example.invalid", "SenhaSegura123!")

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        server.DATABASE = self.previous_database
        self.temporary_directory.cleanup()

    def request(self, method, path, body=None, *, authenticated=True):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        return response.code, json.loads(response.read().decode("utf-8"))

    def login(self, email, password):
        status, response = self.request("POST", "/api/login", {"email": email, "password": password})
        self.assertEqual(status, 200)
        self.token = response["token"]
        return response["user"]

    def make_admin(self):
        with server.connect() as connection:
            connection.execute("UPDATE users SET role = 'ADMINISTRADOR' WHERE id = ?", (self.user_id,))
        self.login("orientador@example.invalid", "SenhaSegura123!")

    def import_example_data(self):
        status, project = self.request("POST", "/api/projects", {
                "name": "Pesquisa da água",
                "program": "PIBIC",
                "coordinator": "Docente Exemplo",
                "unit": "Instituto de Ciências Exatas",
                "start": "2026-03-01",
                "end": "2027-02-28",
                "status": "Em andamento",
                "progress": 35,
        })
        self.assertEqual(status, 201)
        status, person = self.request("POST", "/api/people", {
                "name": "Estudante Exemplo",
                "email": "estudante@example.invalid",
                "role": "Aluno(a)",
                "unit": "Instituto de Ciências Exatas",
                "projectId": project["id"],
        })
        self.assertEqual(status, 201)
        status, activity = self.request("POST", "/api/tasks", {
                "title": "Coletar amostras",
                "projectId": project["id"],
                "responsibleId": person["id"],
                "dueDate": "2026-12-01",
                "status": "Pendente",
                "type": "Pesquisa",
        })
        self.assertEqual(status, 201)
        status, event = self.request("POST", "/api/events", {
                "title": "Reunião de orientação",
                "projectId": project["id"],
                "activityId": activity["id"],
                "responsibleId": person["id"],
                "participantIds": [person["id"]],
                "type": "Orientação",
                "startAt": "2026-12-01T10:00",
                "endAt": "2026-12-01T11:00",
                "location": "Campus",
                "reminderMinutes": 30,
        })
        self.assertEqual(status, 201)
        return project, person, activity, event

    def test_bootstrap_requires_authenticated_session(self):
        status, response = self.request("GET", "/api/bootstrap", authenticated=False)

        self.assertEqual(status, 401)
        self.assertNotIn("projects", response)

    def test_import_persists_related_projects_activities_and_events(self):
        project, person, activity, event = self.import_example_data()

        status, data = self.request("GET", "/api/bootstrap")

        self.assertEqual(status, 200)
        self.assertEqual(data["projects"][0]["id"], project["id"])
        self.assertEqual(data["activities"][0]["responsibleId"], person["id"])
        self.assertEqual(data["activities"][0]["id"], activity["id"])
        self.assertEqual(data["events"][0]["participantIds"], [person["id"]])
        self.assertEqual(data["events"][0]["id"], event["id"])
        self.assertEqual(data["events"][0]["reminderMinutes"], 30)

    def test_calendar_event_crud_and_invalid_time(self):
        project, person, _, _ = self.import_example_data()
        status, event = self.request("POST", "/api/events", {
            "title": "Apresentação de resultados",
            "projectId": project["id"],
            "participantIds": [person["id"]],
            "type": "Apresentação",
            "startAt": "2026-12-04T14:00",
            "endAt": "2026-12-04T15:00",
            "reminderMinutes": 10,
        })
        self.assertEqual(status, 201)

        status, _ = self.request("PUT", f"/api/events/{event['id']}", {
            "title": "Apresentação final",
            "projectId": project["id"],
            "participantIds": [person["id"]],
            "type": "Apresentação",
            "startAt": "2026-12-04T14:00",
            "endAt": "2026-12-04T15:00",
            "reminderMinutes": 0,
        })
        self.assertEqual(status, 200)
        status, data = self.request("GET", "/api/events?from=2026-12-04&to=2026-12-04")
        self.assertEqual(status, 200)
        self.assertEqual([item["title"] for item in data["events"]], ["Apresentação final"])

        status, error = self.request("POST", "/api/events", {
            "title": "Horário inválido",
            "projectId": project["id"],
            "startAt": "2026-12-04T15:00",
            "endAt": "2026-12-04T14:00",
        })
        self.assertEqual(status, 400)
        self.assertIn("posterior", error["error"])

        status, _ = self.request("DELETE", f"/api/events/{event['id']}")
        self.assertEqual(status, 200)

    def test_project_participant_and_activity_crud_preserves_references(self):
        status, project = self.request("POST", "/api/projects", {
            "name": "Iniciação científica",
            "program": "PIBIC",
            "coordinator": "Docente Exemplo",
            "unit": "Instituto de Ciências Exatas",
            "start": "2026-03-01",
            "end": "2027-02-28",
            "progress": 20,
            "status": "Em andamento",
        })
        self.assertEqual(status, 201)
        project_id = project["id"]

        status, person = self.request("POST", "/api/people", {
            "name": "Estudante Exemplo",
            "email": "estudante@example.invalid",
            "role": "Aluno(a)",
            "unit": "Instituto de Ciências Exatas",
            "projectId": project_id,
        })
        self.assertEqual(status, 201)
        person_id = person["id"]

        status, activity = self.request("POST", "/api/tasks", {
            "title": "Preparar relatório",
            "projectId": project_id,
            "responsibleId": person_id,
            "dueDate": "2026-12-10",
            "status": "Pendente",
            "type": "Relatório",
        })
        self.assertEqual(status, 201)

        status, _ = self.request("PUT", f"/api/tasks/{activity['id']}", {
            "title": "Relatório entregue",
            "projectId": project_id,
            "responsibleId": person_id,
            "dueDate": "2026-12-10",
            "status": "Cancelada",
            "type": "Relatório",
        })
        self.assertEqual(status, 200)
        status, _ = self.request("PUT", f"/api/projects/{project_id}", {
            "name": "Iniciação científica atualizada",
            "program": "PIBIC",
            "coordinator": "Docente Exemplo",
            "unit": "Instituto de Ciências Exatas",
            "start": "2026-03-01",
            "end": "2027-02-28",
            "progress": 100,
            "status": "Em andamento",
        })
        self.assertEqual(status, 200)
        self.assertEqual(self.request("GET", "/api/bootstrap")[1]["activities"][0]["status"], "Cancelada")

        status, error = self.request("POST", "/api/tasks", {"title": "Tarefa sem projeto"})
        self.assertEqual(status, 400)
        self.assertIn("projeto", error["error"])

        status, _ = self.request("DELETE", f"/api/projects/{project_id}")
        self.assertEqual(status, 200)
        data = self.request("GET", "/api/bootstrap")[1]
        self.assertEqual(data["people"], [])
        self.assertEqual(data["activities"], [])

    def test_project_accepts_status_values_from_specification(self):
        status, project = self.request("POST", "/api/projects", {
            "name": "Projeto suspenso",
            "program": "PIBIC",
            "status": "Suspenso",
            "progress": 10,
        })

        self.assertEqual(status, 201)
        self.assertEqual(self.request("GET", "/api/bootstrap")[1]["projects"][0]["status"], "Suspenso")
        self.assertTrue(project["id"])

    def test_initial_import_is_atomic_and_refused_after_first_write(self):
        self.make_admin()
        broken_data = {
            "projects": [{
                "id": "invalid",
                "name": "Projeto",
                "program": "PIBIC",
                "start": "2027-02-01",
                "end": "2026-01-01",
            }],
            "people": [],
            "activities": [],
            "events": [],
        }
        status, _ = self.request("POST", "/api/import", broken_data)
        self.assertEqual(status, 400)
        self.assertEqual(self.request("GET", "/api/bootstrap")[1]["projects"], [])

        status, _ = self.request("POST", "/api/projects", {
            "name": "Projeto válido", "program": "PIBIC", "status": "Planejado", "progress": 0,
        })
        self.assertEqual(status, 201)
        status, error = self.request("POST", "/api/import", {
            "projects": [], "people": [], "activities": [], "events": [],
        })
        self.assertEqual(status, 409)
        self.assertIn("já possui dados", error["error"])

    def test_duplicate_email_is_rejected_by_database(self):
        project, _, _, _ = self.import_example_data()
        status, error = self.request("POST", "/api/people", {
            "name": "Pessoa duplicada",
            "email": "ESTUDANTE@EXAMPLE.INVALID",
            "role": "Aluno(a)",
            "projectId": project["id"],
        })
        self.assertEqual(status, 409)
        self.assertIn("banco de dados", error["error"])

    def test_backup_is_downloadable_but_database_file_is_not_public(self):
        self.make_admin()
        backup_request = urllib.request.Request(
            self.base_url + "/api/backup",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        response = urllib.request.urlopen(backup_request, timeout=3)
        self.assertIn("eproject-backup.sqlite3", response.headers["Content-Disposition"])
        self.assertTrue(response.read().startswith(b"SQLite format 3"))

        status, error = self.request("GET", "/data/eproject.sqlite3")
        self.assertEqual(status, 404)
        self.assertIn("não encontrado", error["error"])

    def test_registration_cannot_escalate_role_or_access_another_users_project(self):
        status, project = self.request("POST", "/api/projects", {
            "name": "Projeto privado", "program": "PIBIC", "status": "Planejado", "progress": 0,
        })
        self.assertEqual(status, 201)
        status, registration = self.request("POST", "/api/register", {
            "name": "Segundo usuário",
            "email": "segundo@example.invalid",
            "password": "OutraSenha123!",
            "role": "ADMINISTRADOR",
            "acceptedTerms": True,
            "acceptedPrivacy": True,
        })
        self.assertEqual(status, 201)
        user = self.login("segundo@example.invalid", "OutraSenha123!")
        self.assertEqual(user["role"], "ORIENTANDO")
        self.assertEqual(self.request("GET", "/api/bootstrap")[1]["projects"], [])
        status, _ = self.request("PUT", f"/api/projects/{project['id']}", {
            "name": "Projeto alterado", "program": "PIBIC", "status": "Planejado", "progress": 0,
        })
        self.assertEqual(status, 403)
        self.assertNotEqual(registration["id"], self.user_id)

    def test_legacy_orphan_tasks_are_preserved_during_schema_migration(self):
        previous_database = server.DATABASE
        server.DATABASE = Path(self.temporary_directory.name) / "legacy.sqlite3"
        legacy = server.sqlite3.connect(server.DATABASE)
        try:
            legacy.executescript("""
                CREATE TABLE projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, program TEXT NOT NULL,
                    coordinator TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL DEFAULT '',
                    start_date TEXT, end_date TEXT, status TEXT NOT NULL DEFAULT 'Planejado',
                    progress INTEGER NOT NULL DEFAULT 0, description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE activities (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
                    responsible_id TEXT, due_date TEXT,
                    status TEXT NOT NULL DEFAULT 'Pendente'
                        CHECK (status IN ('Pendente', 'Em andamento', 'Concluída')),
                    type TEXT NOT NULL DEFAULT 'Outro', description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO projects (id, name, program, status, progress)
                    VALUES ('old-project', 'Projeto legado', 'PIBIC', 'Pausado', 0);
                INSERT INTO activities (id, title, project_id) VALUES ('old-task', 'Tarefa legada', NULL);
            """)
        finally:
            legacy.close()

        try:
            server.initialize_database()
            with server.connect() as connection:
                task = connection.execute("SELECT project_id, status FROM activities WHERE id = 'old-task'").fetchone()
                project = connection.execute("SELECT name FROM projects WHERE id = ?", (task["project_id"],)).fetchone()
                old_project = connection.execute("SELECT status FROM projects WHERE id = 'old-project'").fetchone()
                self.assertEqual(task["status"], "Pendente")
                self.assertIn("legados", project["name"])
                self.assertEqual(old_project["status"], "Pausado")
                with self.assertRaises(server.sqlite3.IntegrityError):
                    connection.execute("INSERT INTO activities (id, title, project_id) VALUES ('no-project', 'Sem projeto', NULL)")
                connection.execute(
                    "INSERT INTO activities (id, title, project_id, status) VALUES ('cancelled-task', 'Cancelada', ?, 'Cancelada')",
                    (task["project_id"],),
                )
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            server.DATABASE = previous_database


if __name__ == "__main__":
    unittest.main()
