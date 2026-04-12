-- 已有库补加成交额榜索引（新建库请直接用 scripts/schema.sql）。
-- MySQL 8+：若已存在同名索引会报错，可先 SHOW INDEX FROM daily_kline; 确认后执行。
ALTER TABLE daily_kline
  ADD INDEX ix_daily_kline_trade_date_amount (trade_date, amount);
