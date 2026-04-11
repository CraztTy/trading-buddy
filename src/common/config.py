"""
Trading Buddy - 配置文件
使用 Pydantic Settings 管理配置，支持 .env 文件
"""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _load_env_file() -> None:
    """将项目根目录 .env 写入 os.environ（键在文件中则覆盖，避免 shell 里空变量挡住 .env）。"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()


def _skip_dotenv() -> bool:
    """pytest 等场景下由 tests/conftest 置位，避免测试被本机 .env 劫持。"""
    v = os.environ.get("TRADING_BUDDY_SKIP_DOTENV", "").strip().lower()
    return v in ("1", "true", "yes", "on")


# 启动时加载 .env（测试进程见 TRADING_BUDDY_SKIP_DOTENV）
if not _skip_dotenv():
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

    # MySQL 模式（连接信息以环境变量为准，勿在代码里写死密码）
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    name: str = "trading"
    # 云数据库常用：超时、SSL（阿里云/腾讯云 RDS 等常要求 SSL 或推荐开启）
    connect_timeout: int = 30
    ssl_enabled: bool = False

    def __init__(self, **data):
        # 手动从 os.environ 读取（_load_env_file 已将 .env 加载到环境变量）
        # 优先级：显式传入 > 环境变量 > 默认值
        if "mode" not in data:
            data["mode"] = os.environ.get("DATABASE_MODE", "sqlite")
        if "host" not in data:
            data["host"] = (
                os.environ.get("DATABASE_HOST")
                or os.environ.get("DB_HOST")
                or "localhost"
            )
        if "port" not in data:
            port_val = os.environ.get("DATABASE_PORT") or os.environ.get("DB_PORT")
            if port_val:
                data["port"] = int(port_val)
        if "user" not in data:
            data["user"] = (
                os.environ.get("DATABASE_USER")
                or os.environ.get("DB_USER")
                or "root"
            )
        if "password" not in data:
            data["password"] = (
                os.environ.get("DATABASE_PASSWORD")
                or os.environ.get("DB_PASSWORD")
                or ""
            )
        if "name" not in data:
            data["name"] = (
                os.environ.get("DATABASE_NAME")
                or os.environ.get("DB_NAME")
                or "trading"
            )
        if "connect_timeout" not in data:
            ct = os.environ.get("DATABASE_CONNECT_TIMEOUT") or os.environ.get(
                "DB_CONNECT_TIMEOUT"
            )
            if ct:
                data["connect_timeout"] = int(ct)
        if "ssl_enabled" not in data:
            v = (
                os.environ.get("DATABASE_SSL")
                or os.environ.get("MYSQL_SSL")
                or "false"
            ).strip().lower()
            data["ssl_enabled"] = v in ("1", "true", "yes", "on")
        super().__init__(**data)

    def mysql_connect_args(self) -> dict:
        """pymysql / aiomysql 连接参数（云 MySQL 可配合 DATABASE_SSL）"""
        args: dict = {"connect_timeout": self.connect_timeout}
        if self.ssl_enabled:
            # 空 dict 表示启用 TLS（具体校验由服务端与客户端默认策略决定）
            args["ssl"] = {}
        return args

    @property
    def url(self) -> str:
        """异步数据库连接URL"""
        if self.mode == "sqlite":
            db_path = Path(self.db_path)
            if not db_path.is_absolute():
                db_path = Path(__file__).parent.parent.parent / self.db_path
            return f"sqlite+aiosqlite:///{db_path}"
        u = quote_plus(self.user)
        p = quote_plus(self.password)
        return (
            f"mysql+aiomysql://{u}:{p}@{self.host}:{self.port}/{self.name}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_url(self) -> str:
        """同步数据库连接URL（用于初始化）"""
        if self.mode == "sqlite":
            db_path = Path(self.db_path)
            if not db_path.is_absolute():
                db_path = Path(__file__).parent.parent.parent / self.db_path
            return f"sqlite:///{db_path}"
        u = quote_plus(self.user)
        p = quote_plus(self.password)
        return (
            f"mysql+pymysql://{u}:{p}@{self.host}:{self.port}/{self.name}"
            f"?charset=utf8mb4"
        )


class RedisSettings(BaseSettings):
    """Redis配置（可选，SQLite模式下可禁用）"""
    model_config = SettingsConfigDict(extra="ignore")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    enabled: bool = False  # SQLite模式下默认禁用

    def __init__(self, **data):
        if "host" not in data:
            data["host"] = os.environ.get("REDIS_HOST", "localhost")
        if "port" not in data:
            port_val = os.environ.get("REDIS_PORT")
            if port_val:
                data["port"] = int(port_val)
        if "db" not in data:
            db_val = os.environ.get("REDIS_DB")
            if db_val != "" and db_val is not None:
                data["db"] = int(db_val)
        if "password" not in data:
            p = os.environ.get("REDIS_PASSWORD")
            data["password"] = p if p else None
        if "enabled" not in data:
            v = os.environ.get("REDIS_ENABLED", "false").strip().lower()
            data["enabled"] = v in ("1", "true", "yes", "on")
        super().__init__(**data)

    @property
    def url(self) -> str:
        """Redis连接URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class DataSourceSettings(BaseSettings):
    """数据源配置"""
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "baostock"  # baostock / tushare
    # tushare付费版配置（未来扩展）
    tushare_token: str | None = None

    def __init__(self, **data):
        if "provider" not in data:
            data["provider"] = os.environ.get("DATA_SOURCE", "baostock")
        if "tushare_token" not in data:
            token = os.environ.get("TUSHARE_TOKEN")
            data["tushare_token"] = token if token else None
        super().__init__(**data)


class APISettings(BaseSettings):
    """API 服务（API_HOST / API_PORT / API_DEBUG；实时接口缓存与限流）"""
    model_config = SettingsConfigDict(extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    # /api/realtime/* 短缓存（秒）；REALTIME_CACHE_TTL_SEC
    realtime_cache_ttl_sec: int = 15
    # 每 IP 每分钟允许请求次数；REALTIME_RATE_PER_MINUTE
    realtime_rate_per_minute: int = 60
    # CORS：逗号分隔源列表，或 *；CORS_ORIGINS
    cors_origins: str = "*"

    def __init__(self, **data):
        if "host" not in data:
            data["host"] = os.environ.get("API_HOST", "0.0.0.0").strip() or "0.0.0.0"
        if "port" not in data:
            p = os.environ.get("API_PORT")
            if p:
                data["port"] = int(p.strip())
        if "debug" not in data:
            v = (os.environ.get("API_DEBUG", "false")).strip().lower()
            data["debug"] = v in ("1", "true", "yes", "on")
        if "realtime_cache_ttl_sec" not in data:
            v = os.environ.get("REALTIME_CACHE_TTL_SEC")
            if v:
                data["realtime_cache_ttl_sec"] = max(1, int(v.strip()))
        if "realtime_rate_per_minute" not in data:
            v = os.environ.get("REALTIME_RATE_PER_MINUTE")
            if v:
                data["realtime_rate_per_minute"] = max(1, int(v.strip()))
        if "cors_origins" not in data:
            v = os.environ.get("CORS_ORIGINS")
            if v is not None:
                data["cors_origins"] = v.strip()
        super().__init__(**data)


class LogSettings(BaseSettings):
    """日志（LOG_LEVEL）"""
    model_config = SettingsConfigDict(extra="ignore")

    level: str = "INFO"
    format: str = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"

    def __init__(self, **data):
        if "level" not in data:
            lv = os.environ.get("LOG_LEVEL")
            if lv:
                data["level"] = lv.strip().upper()
        super().__init__(**data)


class Settings(BaseSettings):
    """全局配置

    不显式接入 EnvSettingsSource：否则 `DATA_SOURCE=baostock` 会被当成嵌套字段
    `data_source` 的 JSON。数据库/数据源等均由子 Settings 的 __init__ 读 os.environ
   （在 _load_env_file() 之后）。
    """

    model_config = SettingsConfigDict(extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)

    # 各模块配置（default_factory 避免子配置实例在类加载时被共享）
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    data_source: DataSourceSettings = Field(default_factory=DataSourceSettings)
    api: APISettings = Field(default_factory=APISettings)
    log: LogSettings = Field(default_factory=LogSettings)

    # 项目根目录
    project_root: Path = Path(__file__).parent.parent.parent


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


def cors_allow_origins() -> list[str]:
    """供 FastAPI CORSMiddleware：* 或逗号分隔 URL。"""
    raw = get_settings().api.cors_origins.strip()
    if not raw or raw == "*":
        return ["*"]
    return [x.strip() for x in raw.split(",") if x.strip()]


def describe_database_write_target() -> str:
    """供脚本打印：实际写入的数据库位置（不含密码）。"""
    db = get_settings().database
    if db.mode == "sqlite":
        p = Path(db.db_path)
        if not p.is_absolute():
            p = Path(__file__).parent.parent.parent / db.db_path
        return f"SQLite → {p.resolve()}"
    return f"MySQL → {db.user}@{db.host}:{db.port}/{db.name}"
