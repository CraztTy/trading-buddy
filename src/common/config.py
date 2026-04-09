"""
Trading Buddy - 配置文件
使用 Pydantic Settings 管理配置，支持 .env 文件
"""

import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_env_file() -> dict[str, str]:
    """手动加载 .env 文件到环境变量"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


# 启动时加载 .env
_load_env_file()


class DatabaseSettings(BaseSettings):
    """数据库配置

    环境变量使用 DATABASE_MODE / DATABASE_HOST 等格式（在 .env 中定义），
    由模块级 _load_env_file() 加载到 os.environ
    """
    model_config = SettingsConfigDict(extra="ignore")

    # SQLite 模式 (默认)
    mode: str = "sqlite"
    db_path: str = "data/trading.db"

    # MySQL 模式 (生产环境使用)
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = "trading2024"
    name: str = "trading"

    def __init__(self, **data):
        # 手动从 os.environ 读取（_load_env_file 已将 .env 加载到环境变量）
        # 优先级：显式传入 > 环境变量 > 默认值
        if "mode" not in data:
            data["mode"] = os.environ.get("DATABASE_MODE", "sqlite")
        if "host" not in data:
            data["host"] = os.environ.get("DATABASE_HOST", "localhost")
        if "port" not in data:
            port_val = os.environ.get("DATABASE_PORT")
            if port_val:
                data["port"] = int(port_val)
        if "user" not in data:
            data["user"] = os.environ.get("DATABASE_USER", "root")
        if "password" not in data:
            data["password"] = os.environ.get("DATABASE_PASSWORD", "")
        if "name" not in data:
            data["name"] = os.environ.get("DATABASE_NAME", "trading")
        super().__init__(**data)

    @property
    def url(self) -> str:
        """异步数据库连接URL"""
        if self.mode == "sqlite":
            db_path = Path(self.db_path)
            if not db_path.is_absolute():
                db_path = Path(__file__).parent.parent.parent / self.db_path
            return f"sqlite+aiosqlite:///{db_path}"
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        """同步数据库连接URL（用于初始化）"""
        if self.mode == "sqlite":
            db_path = Path(self.db_path)
            if not db_path.is_absolute():
                db_path = Path(__file__).parent.parent.parent / self.db_path
            return f"sqlite:///{db_path}"
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis配置（可选，SQLite模式下可禁用）"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    enabled: bool = False  # SQLite模式下默认禁用

    @property
    def url(self) -> str:
        """Redis连接URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class DataSourceSettings(BaseSettings):
    """数据源配置"""
    provider: str = "baostock"  # baostock / tushare
    # tushare付费版配置（未来扩展）
    tushare_token: str | None = None


class APISettings(BaseSettings):
    """API服务配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class LogSettings(BaseSettings):
    """日志配置"""
    level: str = "INFO"
    format: str = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"


class Settings(BaseSettings):
    """全局配置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # 各模块配置
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    data_source: DataSourceSettings = DataSourceSettings()
    api: APISettings = APISettings()
    log: LogSettings = LogSettings()

    # 项目根目录
    project_root: Path = Path(__file__).parent.parent.parent


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
