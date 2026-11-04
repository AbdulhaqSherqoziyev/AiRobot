from alembic import context
from sqlalchemy import create_engine

from quantlab.config import get_settings
from quantlab.models import Base

url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url
engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=url.startswith("sqlite"), compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
