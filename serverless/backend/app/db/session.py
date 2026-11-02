from app.core.config import settings
from app.db.engine import create_database_engine

# Lambda reuses module state between warm invocations, so each execution
# environment also reuses this bounded pool.
engine = create_database_engine(settings)
