"""Small SQL-backed transport for exercising services without a hosted REST API.

It implements only the fluent operations used by the tested services. Filtering,
constraints, transactions and RPC bodies execute in real PostgreSQL.
"""

import json
from types import SimpleNamespace


def literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, dict | list):
        return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


class PostgresDatabase:
    def __init__(self, execute):
        self.execute = execute

    def table(self, name):
        return PostgresQuery(self.execute, name)

    def rpc(self, name, params):
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(
                data=self._json(
                    "SET ROLE service_role; SELECT "
                    + name
                    + "("
                    + ",".join(f"{key} => {literal(value)}" for key, value in params.items())
                    + ");"
                )
            )
        )

    def _json(self, statement):
        return json.loads(self.execute(statement))


class PostgresQuery:
    def __init__(self, execute, name):
        self.database = PostgresDatabase(execute)
        self.name = name
        self.filters = []
        self.one = False
        self.maximum = None
        self.payload = None
        self.operation = None

    def select(self, _fields):
        return self

    def update(self, payload):
        self.operation, self.payload = "update", payload
        return self

    def insert(self, payload):
        self.operation, self.payload = "insert", payload
        return self

    def eq(self, field, value):
        self.filters.append(f"{field} = {literal(value)}")
        return self

    def in_(self, field, values):
        self.filters.append(f"{field} IN ({','.join(literal(value) for value in values)})")
        return self

    def limit(self, maximum):
        self.maximum = int(maximum)
        return self

    def single(self):
        self.one = True
        return self

    def execute(self):
        where = " AND ".join(self.filters) or "true"
        limit = f" LIMIT {self.maximum}" if self.maximum is not None else ""
        if self.operation:
            if self.operation == "insert":
                mutation = (
                    f"INSERT INTO {self.name} ({','.join(self.payload)}) VALUES "
                    f"({','.join(literal(value) for value in self.payload.values())})"
                )
            else:
                changes = ",".join(f"{key}={literal(value)}" for key, value in self.payload.items())
                mutation = f"UPDATE {self.name} SET {changes} WHERE {where}"
            return SimpleNamespace(
                data=self.database._json(
                    f"SET ROLE service_role; WITH changed AS ({mutation} RETURNING *) "
                    "SELECT coalesce(jsonb_agg(to_jsonb(changed)), '[]') FROM changed;"
                )
            )
        data = self.database._json(
            f"SET ROLE service_role; SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]') "
            f"FROM (SELECT * FROM {self.name} WHERE {where}{limit}) t;"
        )
        return SimpleNamespace(data=(data[0] if data else None) if self.one else data)
