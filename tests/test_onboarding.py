from fastapi.testclient import TestClient

from app.main import app
from app.services import database
from app.services.auth import hash_password


def test_tour_preference_requires_member_and_is_account_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    password = "Synthetic-tour-passphrase-29"
    clients = []
    for name, role in [("tour-a", "member"), ("tour-b", "member"), ("tour-owner", "owner")]:
        database.create_user_in_db(name, hash_password(password), role=role)
        client = TestClient(app)
        assert client.post("/auth/login", json={"username": name, "password": password}).status_code == 200
        clients.append(client)
    first, second, owner = clients
    assert TestClient(app).get("/api/onboarding").status_code == 401
    assert owner.get("/api/onboarding").status_code == 403
    assert owner.put("/api/onboarding", json={"dismissed": True}).status_code == 403
    assert first.get("/api/onboarding").json() == {"dismissed": False}
    assert first.put("/api/onboarding", json={"dismissed": True}).json() == {"dismissed": True}
    assert first.get("/api/onboarding").json() == {"dismissed": True}
    assert second.get("/api/onboarding").json() == {"dismissed": False}
    assert first.put("/api/onboarding", json={"dismissed": "yes"}).status_code == 422
    for client in clients:
        client.close()
