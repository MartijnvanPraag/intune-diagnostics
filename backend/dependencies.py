import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./intune_diagnostics.db")
# Reduce verbosity: disable SQL echo (can re-enable by setting SQL_ECHO=1)
SQL_ECHO = os.getenv("SQL_ECHO", "0").lower() in ("1", "true", "yes")
engine = create_async_engine(DATABASE_URL, echo=SQL_ECHO)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session_maker() as session:
        yield session