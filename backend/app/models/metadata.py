"""The single SQLAlchemy MetaData object Alembic autogenerate diffs against.

Every relational table gets a Core Table definition registered here, including tables
we only ever query with raw SQL — without a definition there is nothing for
`alembic revision --autogenerate` to compare the live database to, and the migration
comes out empty.
"""

from sqlalchemy import MetaData

metadata = MetaData()

# TODO: define Table(...) objects against `metadata`, one per relational table.
