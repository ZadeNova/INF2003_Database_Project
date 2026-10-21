"""One connection policy for Django and offline PostgreSQL tools (no Django import)."""
import os
from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict


def connection_parameters(database_url=None, *, environ=None):
    env = os.environ if environ is None else environ
    if database_url:
        try:
            params = conninfo_to_dict(database_url)
        except ProgrammingError:
            raise ValueError("Invalid PostgreSQL connection string") from None
        if set(params) - {"dbname", "user", "password", "host", "port", "sslmode"}:
            raise ValueError("Unsupported PostgreSQL connection string option")
    else:
        params = {key: env.get(name, "") for key, name in (
            ("dbname", "POSTGRES_DB"), ("user", "POSTGRES_USER"),
            ("password", "POSTGRES_PASSWORD"), ("host", "POSTGRES_HOST"))}
        params["port"] = env.get("POSTGRES_PORT", "5432")
    for key in ("dbname", "user", "password", "host"):
        if not params.get(key) or params[key].startswith("replace-"):
            raise ValueError("Missing PostgreSQL connection configuration")
    params["sslmode"] = params.get("sslmode", env.get("POSTGRES_SSLMODE")) or "disable"
    params["connect_timeout"] = 10
    return params
