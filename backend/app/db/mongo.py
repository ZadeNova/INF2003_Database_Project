"""MongoDB access via Motor (async, matching asyncpg's driver architecture).

Wiring only — no queries here.
"""

# TODO: AsyncIOMotorClient built from settings, lifespan startup/shutdown, and the
#       FastAPI dependency that yields the database handle.
