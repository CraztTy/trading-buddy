-- =============================================
-- daily_kline 数据迁移脚本（旧表 -> v2 表）
-- =============================================
-- 说明：
-- 1. 旧表有 id/created_at，新表没有，SELECT 时只取业务字段
-- 2. 当前 27 万行可直接一次性 INSERT ... SELECT
-- 3. 若未来数据量 > 500 万行，建议改为按年份分批迁移

USE trading;

-- 清空目标表（幂等，可安全重复执行）
TRUNCATE TABLE daily_kline_v2;

-- 迁移数据
INSERT INTO daily_kline_v2 (
    code,
    trade_date,
    adjust_flag,
    open,
    high,
    low,
    close,
    pre_close,
    volume,
    amount,
    change_pct,
    turnover_rate
)
SELECT
    code,
    trade_date,
    adjust_flag,
    open,
    high,
    low,
    close,
    pre_close,
    volume,
    amount,
    change_pct,
    turnover_rate
FROM daily_kline;

-- 验证行数是否一致
SELECT
    (SELECT COUNT(*) FROM daily_kline) AS old_rows,
    (SELECT COUNT(*) FROM daily_kline_v2) AS new_rows;
