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
        if "db_path" not in data:
            dp = os.environ.get("DATABASE_SQLITE_PATH") or os.environ.get(
                "DATABASE_DB_PATH"
            )
            if dp is not None and str(dp).strip():
                data["db_path"] = str(dp).strip()
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


def _path_ignore_prefixes_from_env(
    env_key: str, *, default_when_unset: tuple[str, ...]
) -> tuple[str, ...]:
    """逗号分隔路径前缀；未设置或空串用 default；``none`` 表示不忽略。"""
    raw = os.environ.get(env_key)
    if raw is None or str(raw).strip() == "":
        return default_when_unset
    if str(raw).strip().lower() == "none":
        return ()
    parts: list[str] = []
    for p in str(raw).split(","):
        s = p.strip()
        if not s:
            continue
        if not s.startswith("/"):
            s = "/" + s
        parts.append(s)
    return tuple(parts)


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
    # 逐请求一行访问日志（方法、路径、状态码、耗时 ms）；API_ACCESS_LOG，默认关
    access_log: bool = False
    # 访问日志不记录的路径前缀；未设环境变量时默认 ("/health",)；none 表示全记
    access_log_ignore_prefixes: tuple[str, ...] = ("/health",)
    # 单请求 wall-clock ≥ 该毫秒数时打 WARN（http.slow）；0 关闭。API_SLOW_REQUEST_WARN_MS
    slow_request_warn_ms: int = 0
    # 慢请求 WARN 忽略的路径前缀（逗号分隔）；未设置环境变量时默认 ("/health",)；none 表示不忽略
    slow_request_ignore_prefixes: tuple[str, ...] = ("/health",)

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
        if "access_log" not in data:
            v = (os.environ.get("API_ACCESS_LOG", "false") or "").strip().lower()
            data["access_log"] = v in ("1", "true", "yes", "on")
        if "slow_request_warn_ms" not in data:
            raw = os.environ.get("API_SLOW_REQUEST_WARN_MS")
            if raw is not None and str(raw).strip() != "":
                try:
                    ms = int(str(raw).strip())
                    data["slow_request_warn_ms"] = max(0, min(ms, 3_600_000))
                except ValueError:
                    data["slow_request_warn_ms"] = 0
        if "slow_request_ignore_prefixes" not in data:
            data["slow_request_ignore_prefixes"] = _path_ignore_prefixes_from_env(
                "API_SLOW_REQUEST_IGNORE_PREFIXES", default_when_unset=("/health",)
            )
        if "access_log_ignore_prefixes" not in data:
            data["access_log_ignore_prefixes"] = _path_ignore_prefixes_from_env(
                "API_ACCESS_LOG_IGNORE_PREFIXES", default_when_unset=("/health",)
            )
        super().__init__(**data)


class AuthSettings(BaseSettings):
    """认证配置（JWT、AUTH_REQUIRED）"""

    model_config = SettingsConfigDict(extra="ignore")

    auth_required: bool = False
    jwt_secret: str = "trading-buddy-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    def __init__(self, **data):
        if "auth_required" not in data:
            v = (os.environ.get("AUTH_REQUIRED", "false") or "").strip().lower()
            data["auth_required"] = v in ("1", "true", "yes", "on")
        if "jwt_secret" not in data:
            secret = os.environ.get("JWT_SECRET")
            if secret:
                data["jwt_secret"] = secret
        if "jwt_algorithm" not in data:
            algo = os.environ.get("JWT_ALGORITHM")
            if algo:
                data["jwt_algorithm"] = algo
        if "jwt_access_token_expire_minutes" not in data:
            raw = os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
            if raw:
                data["jwt_access_token_expire_minutes"] = int(raw)
        super().__init__(**data)


class LogSettings(BaseSettings):
    """日志（LOG_LEVEL、LOG_JSON）"""

    model_config = SettingsConfigDict(extra="ignore")

    level: str = "INFO"
    format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level> | "
        "<dim>rid={extra[request_id]}</dim>"
    )
    json_logs: bool = False

    def __init__(self, **data):
        if "level" not in data:
            lv = os.environ.get("LOG_LEVEL")
            if lv:
                data["level"] = lv.strip().upper()
        if "json_logs" not in data:
            v = (os.environ.get("LOG_JSON", "false") or "").strip().lower()
            data["json_logs"] = v in ("1", "true", "yes", "on")
        super().__init__(**data)


class BrokerSettings(BaseSettings):
    """券商/交易适配器配置。

    - ``BROKER_ADAPTER``: 默认适配器类型，可选 ``paper`` / ``xtquant``
    - ``XTQUANT_QMT_PATH``: miniQMT userdata 路径（Windows），如 ``C:\\国金QMT交易端\\userdata_mini``
    - ``XTQUANT_ACCOUNT_ID``: 资金账号
    - ``XTQUANT_SESSION_ID``: 会话 ID（须唯一）
    """

    model_config = SettingsConfigDict(extra="ignore")

    adapter: str = "paper"
    xtquant_qmt_path: str = ""
    xtquant_account_id: str = ""
    xtquant_session_id: int = 123456

    def __init__(self, **data):
        if "adapter" not in data:
            v = os.environ.get("BROKER_ADAPTER")
            if v is not None:
                data["adapter"] = str(v).strip().lower()
        if "xtquant_qmt_path" not in data:
            v = os.environ.get("XTQUANT_QMT_PATH")
            if v is not None:
                data["xtquant_qmt_path"] = str(v).strip()
        if "xtquant_account_id" not in data:
            v = os.environ.get("XTQUANT_ACCOUNT_ID")
            if v is not None:
                data["xtquant_account_id"] = str(v).strip()
        if "xtquant_session_id" not in data:
            v = os.environ.get("XTQUANT_SESSION_ID")
            if v is not None and str(v).strip():
                try:
                    data["xtquant_session_id"] = int(str(v).strip())
                except ValueError:
                    pass
        super().__init__(**data)


class ClickHouseSettings(BaseSettings):
    """ClickHouse 时序数据库配置。

    - ``CLICKHOUSE_ENABLED``: 是否启用 ClickHouse
    - ``CLICKHOUSE_HOST``: 主机地址
    - ``CLICKHOUSE_PORT``: HTTP 端口（默认 8123）
    - ``CLICKHOUSE_USER``: 用户名
    - ``CLICKHOUSE_PASSWORD``: 密码
    - ``CLICKHOUSE_DATABASE``: 数据库名（默认 trading）
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = False
    host: str = "localhost"
    port: int = 8123
    user: str = "default"
    password: str = ""
    database: str = "trading"

    def __init__(self, **data):
        if "enabled" not in data:
            v = os.environ.get("CLICKHOUSE_ENABLED", "").strip().lower()
            data["enabled"] = v in ("1", "true", "yes", "on")
        if "host" not in data:
            data["host"] = os.environ.get("CLICKHOUSE_HOST", "localhost")
        if "port" not in data:
            p = os.environ.get("CLICKHOUSE_PORT", "")
            if p:
                data["port"] = int(p)
        if "user" not in data:
            data["user"] = os.environ.get("CLICKHOUSE_USER", "default")
        if "password" not in data:
            data["password"] = os.environ.get("CLICKHOUSE_PASSWORD", "")
        if "database" not in data:
            data["database"] = os.environ.get("CLICKHOUSE_DATABASE", "trading")
        super().__init__(**data)


class TradeCalendarSettings(BaseSettings):
    """交易日历：看板下拉等用的 exchange 列表（环境变量配置）。

    - ``TRADE_CALENDAR_EXCHANGE_OPTIONS``：逗号分隔，如 ``cn,hk,us``（最长 32、小写存储）。
    - ``TRADE_CALENDAR_DEFAULT_EXCHANGE``：默认选中项，须出现在列表中；空或未命中则用列表首项。
    """

    model_config = SettingsConfigDict(extra="ignore")

    exchange_options_csv: str = "cn"
    default_exchange: str = ""

    def __init__(self, **data):
        if "exchange_options_csv" not in data:
            v = os.environ.get("TRADE_CALENDAR_EXCHANGE_OPTIONS")
            if v is not None and str(v).strip():
                data["exchange_options_csv"] = str(v).strip()
        if "default_exchange" not in data:
            v = os.environ.get("TRADE_CALENDAR_DEFAULT_EXCHANGE")
            if v is not None:
                data["default_exchange"] = str(v).strip()
        super().__init__(**data)

    def exchange_option_values(self) -> list[str]:
        parts = [p.strip().lower() for p in self.exchange_options_csv.split(",")]
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if not p or len(p) > 32:
                continue
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out if out else ["cn"]

    def resolved_default_exchange(self) -> str:
        opts = self.exchange_option_values()
        d = self.default_exchange.strip().lower()
        if d and d in opts:
            return d
        return opts[0]


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
    auth: AuthSettings = Field(default_factory=AuthSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    clickhouse: ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    trade_calendar: TradeCalendarSettings = Field(default_factory=TradeCalendarSettings)

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
