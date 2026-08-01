from app.users import service


class Result:
    def __init__(self, rows=None, rowcount=0):
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self):
        self.calls = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))
        if "information_schema.columns" in query:
            return Result([{"column_name": "role"}, {"column_name": "user_type"}])
        return Result(rowcount=2)

    def commit(self):
        self.committed = True


def test_legacy_profesor_values_are_migrated_to_docente_in_database(monkeypatch) -> None:
    connection = Connection()
    monkeypatch.setattr(service, "_connect", lambda: connection)

    updated = service.migrate_legacy_user_types()

    updates = [call for call in connection.calls if call[1]]
    assert updated == 4
    assert len(updates) == 2
    assert all(params == ("docente", "profesor") for _query, params in updates)
    assert connection.committed
