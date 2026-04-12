-- 已有 SQLite 库补加成交额榜索引（新建库由 SQLAlchemy create_all 随模型创建）。
-- 在 sqlite3 CLI 中：.open your.db 后执行本文件，或 sqlite3 your.db < scripts/alter_daily_kline_trade_date_amount_index_sqlite.sql
CREATE INDEX IF NOT EXISTS ix_daily_kline_trade_date_amount ON daily_kline (trade_date, amount);
