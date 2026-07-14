"""Load test for LMS IDE-SP API.

Usage:
    pip install locust
    locust -f scripts/locustfile.py --host=https://your-app.fly.dev
    # Open http://localhost:8089, set 50 users, 10 spawn rate
"""

import uuid

from locust import FastHttpUser, between, task


class LMSUser(FastHttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Register a new user on start."""
        self.email = f"loadtest_{uuid.uuid4().hex[:8]}@test.com"
        self.password = "Test@123456"
        self.token = None
        self.user_id = None
        self.curso_id = None

        r = self.client.post(
            "/api/v1/auth/registro",
            json={
                "nome_completo": "Load Test User",
                "email": self.email,
                "senha": self.password,
                "aceite_lgpd": True,
            },
        )
        if r.status_code == 201:
            data = r.json()
            self.user_id = data.get("id")

    @task(3)
    def login(self):
        r = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.email, "senha": self.password},
        )
        if r.status_code == 200:
            self.token = r.json().get("access_token")
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    @task(2)
    def list_cursos(self):
        self.client.get("/api/v1/cursos")

    @task(2)
    def list_trilhas(self):
        self.client.get("/api/v1/trilhas")

    @task(1)
    def dashboard_resumo(self):
        self.client.get("/api/v1/dashboard/resumo")

    @task(1)
    def meu_progresso(self):
        if self.token:
            self.client.get("/api/v1/dashboard/meu-progresso")

    @task(1)
    def list_avaliacoes(self):
        self.client.get("/api/v1/avaliacoes")

    @task(1)
    def gamificacao_niveis(self):
        self.client.get("/api/v1/gamificacao/niveis")

    @task(1)
    def list_sessoes(self):
        self.client.get("/api/v1/sessoes")

    def on_stop(self):
        """Cleanup: delete self if created."""
        if self.user_id and self.token:
            self.client.delete(f"/api/v1/usuarios/{self.user_id}")
