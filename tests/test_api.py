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

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        server.DATABASE = self.previous_database
        self.temporary_directory.cleanup()

    def request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        return response.code, json.loads(response.read().decode("utf-8"))

    def import_example_data(self):
        return self.request("POST", "/api/import", {
            "projects": [{
                "id": "p1",
                "name": "Pesquisa da água",
                "program": "PIBIC",
                "coordinator": "Docente Exemplo",
                "unit": "Instituto de Ciências Exatas",
                "start": "2026-03-01",
                "end": "2027-02-28",
                "status": "Em andamento",
                "progress": 35,
            }],
            "people": [{
                "id": "u1",
                "name": "Estudante Exemplo",
                "email": "estudante@example.invalid",
                "role": "Aluno(a)",
                "unit": "Instituto de Ciências Exatas",
                "projectId": "p1",
            }],
            "activities": [{
                "id": "a1",
                "title": "Coletar amostras",
                "projectId": "p1",
                "responsibleId": "u1",
                "dueDate": "2026-12-01",
                "status": "Pendente",
                "type": "Pesquisa",
            }],
            "events": [{
                "id": "e1",
                "title": "Reunião de orientação",
                "projectId": "p1",
                "activityId": "a1",
                "responsibleId": "u1",
                "participantIds": ["u1"],
                "type": "Orientação",
                "startAt": "2026-12-01T10:00",
                "endAt": "2026-12-01T11:00",
                "location": "Campus",
                "reminderMinutes": 30,
            }],
        })

    def test_import_persists_related_projects_activities_and_events(self):
        status, _ = self.import_example_data()
        self.assertEqual(status, 201)

        status, data = self.request("GET", "/api/bootstrap")

        self.assertEqual(status, 200)
        self.assertEqual(data["projects"][0]["id"], "p1")
        self.assertEqual(data["activities"][0]["responsibleId"], "u1")
        self.assertEqual(data["events"][0]["participantIds"], ["u1"])
        self.assertEqual(data["events"][0]["reminderMinutes"], 30)

    def test_calendar_event_crud_and_invalid_time(self):
        self.import_example_data()
        status, event = self.request("POST", "/api/events", {
            "title": "Apresentação de resultados",
            "projectId": "p1",
            "participantIds": ["u1"],
            "type": "Apresentação",
            "startAt": "2026-12-04T14:00",
            "endAt": "2026-12-04T15:00",
            "reminderMinutes": 10,
        })
        self.assertEqual(status, 201)

        status, _ = self.request("PUT", f"/api/events/{event['id']}", {
            "title": "Apresentação final",
            "projectId": "p1",
            "participantIds": ["u1"],
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

        status, activity = self.request("POST", "/api/activities", {
            "title": "Preparar relatório",
            "projectId": project_id,
            "responsibleId": person_id,
            "dueDate": "2026-12-10",
            "status": "Pendente",
            "type": "Relatório",
        })
        self.assertEqual(status, 201)

        status, _ = self.request("PUT", f"/api/activities/{activity['id']}", {
            "title": "Relatório entregue",
            "projectId": project_id,
            "responsibleId": person_id,
            "dueDate": "2026-12-10",
            "status": "Concluída",
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
        self.assertEqual(self.request("GET", "/api/bootstrap")[1]["activities"][0]["status"], "Concluída")

        status, _ = self.request("DELETE", f"/api/projects/{project_id}")
        self.assertEqual(status, 200)
        data = self.request("GET", "/api/bootstrap")[1]
        self.assertIsNone(data["people"][0]["projectId"])
        self.assertIsNone(data["activities"][0]["projectId"])
        self.assertEqual(data["activities"][0]["responsibleId"], person_id)

    def test_initial_import_is_atomic_and_refused_after_first_write(self):
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

        self.import_example_data()
        status, error = self.import_example_data()
        self.assertEqual(status, 409)
        self.assertIn("já possui dados", error["error"])

    def test_duplicate_email_is_rejected_by_database(self):
        self.import_example_data()
        status, error = self.request("POST", "/api/people", {
            "name": "Pessoa duplicada",
            "email": "ESTUDANTE@EXAMPLE.INVALID",
            "role": "Aluno(a)",
            "projectId": "p1",
        })
        self.assertEqual(status, 409)
        self.assertIn("banco de dados", error["error"])

    def test_backup_is_downloadable_but_database_file_is_not_public(self):
        response = urllib.request.urlopen(self.base_url + "/api/backup", timeout=3)
        self.assertIn("eproject-backup.sqlite3", response.headers["Content-Disposition"])
        self.assertTrue(response.read().startswith(b"SQLite format 3"))

        status, error = self.request("GET", "/data/eproject.sqlite3")
        self.assertEqual(status, 404)
        self.assertIn("não encontrado", error["error"])


if __name__ == "__main__":
    unittest.main()
