"""
Trading Buddy - 数据库连接管理
支持 SQLite (开发模式) 和 MySQL (生产模式)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.common import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy 基类"""
    pass


class Database:
    """数据库连接管理器"""
    
    def __init__(self):
        settings = get_settings()
        
        if settings.database.mode == "sqlite":
            # SQLite 配置
            self._engine = create_async_engine(
                settings.database.url,
                echo=settings.api.debug,
                connect_args={"check_same_thread": False}  # SQLite 特定
            )
        else:
            # MySQL 配置
            self._engine = create_async_engine(
                settings.database.url,
                echo=settings.api.debug,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
            )
        
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取数据库会话"""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """上下文管理器方式获取会话"""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def close(self) -> None:
        """关闭数据库连接"""
        await self._engine.dispose()
    
    async def create_tables(self):
        """创建所有表"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


# 全局数据库实例
_db: Database | None = None


def get_database() -> Database:
    """获取数据库实例"""
    global _db
    if _db is None:
        _db = Database()
    return _db


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """依赖注入用的会话获取函数"""
    db = get_database()
    async for session in db.get_session():
        yield session
