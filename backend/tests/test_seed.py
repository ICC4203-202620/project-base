from uuid import UUID, uuid4

from app.db import seed as seed_module


class FakeConnection:
    def __init__(self, existing_user_id=None):
        self.existing_user_id = existing_user_id
        self.inserted_values = None

    def scalar(self, statement):
        return self.existing_user_id

    def execute(self, statement):
        self.inserted_values = statement.compile().params

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return self.connection


def test_seed_creates_development_user_once(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(seed_module, "engine", FakeEngine(connection))
    monkeypatch.setattr(seed_module.settings, "seed_demo_user", True)

    assert seed_module.seed() is True
    assert connection.inserted_values["email"] == "demo@foodie.local"
    assert connection.inserted_values["handle"] == "@demo"
    assert isinstance(connection.inserted_values["id"], UUID)


def test_seed_skips_existing_user(monkeypatch):
    connection = FakeConnection(existing_user_id=uuid4())
    monkeypatch.setattr(seed_module, "engine", FakeEngine(connection))
    monkeypatch.setattr(seed_module.settings, "seed_demo_user", True)

    assert seed_module.seed() is False
    assert connection.inserted_values is None
