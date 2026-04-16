-- =============================================
-- daily_kline 表结构重构（按年分区 + 复合主键）
-- =============================================
-- 目标：
-- 1. 去掉无意义的自增 id 主键，改用 (code, trade_date, adjust_flag) 复合主键
-- 2. 按 trade_date 做 RANGE 分区，单标回测只命中相关年份分区
-- 3. 去掉 created_at 字段（时间序列数据不需要审计字段）
-- 4. 保留涨跌榜/成交额榜业务索引
--
-- 当前数据量预估（20 年 × 3 复权档）：
--   ~7,000 万行，按年分区后单分区 ~350 万行，查询 I/O 减少 80%+

USE trading;

-- 先删除旧表（如果之前存在）
DROP TABLE IF EXISTS daily_kline_v2;

-- 创建新表
CREATE TABLE daily_kline_v2 (
    code VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    adjust_flag VARCHAR(2) NOT NULL DEFAULT '3',
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    pre_close DECIMAL(10, 2) COMMENT '前收盘价',
    volume BIGINT COMMENT '成交量（股）；指数日为全市场合计',
    amount DECIMAL(20, 2) COMMENT '成交额（元）',
    change_pct DECIMAL(10, 4) COMMENT '涨跌幅%',
    turnover_rate DECIMAL(10, 4) COMMENT '换手率%',

    PRIMARY KEY (code, trade_date, adjust_flag),

    -- 涨跌榜：WHERE trade_date=? ORDER BY change_pct LIMIT N
    INDEX ix_trade_date_pct (trade_date, change_pct),

    -- 成交额榜：WHERE trade_date=? ORDER BY amount DESC LIMIT N
    INDEX ix_trade_date_amount (trade_date, amount)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE COLUMNS(trade_date) (
    PARTITION p2005 VALUES LESS THAN ('2005-01-01'),
    PARTITION p2006 VALUES LESS THAN ('2006-01-01'),
    PARTITION p2007 VALUES LESS THAN ('2007-01-01'),
    PARTITION p2008 VALUES LESS THAN ('2008-01-01'),
    PARTITION p2009 VALUES LESS THAN ('2009-01-01'),
    PARTITION p2010 VALUES LESS THAN ('2010-01-01'),
    PARTITION p2011 VALUES LESS THAN ('2011-01-01'),
    PARTITION p2012 VALUES LESS THAN ('2012-01-01'),
    PARTITION p2013 VALUES LESS THAN ('2013-01-01'),
    PARTITION p2014 VALUES LESS THAN ('2014-01-01'),
    PARTITION p2015 VALUES LESS THAN ('2015-01-01'),
    PARTITION p2016 VALUES LESS THAN ('2016-01-01'),
    PARTITION p2017 VALUES LESS THAN ('2017-01-01'),
    PARTITION p2018 VALUES LESS THAN ('2018-01-01'),
    PARTITION p2019 VALUES LESS THAN ('2019-01-01'),
    PARTITION p2020 VALUES LESS THAN ('2020-01-01'),
    PARTITION p2021 VALUES LESS THAN ('2021-01-01'),
    PARTITION p2022 VALUES LESS THAN ('2022-01-01'),
    PARTITION p2023 VALUES LESS THAN ('2023-01-01'),
    PARTITION p2024 VALUES LESS THAN ('2024-01-01'),
    PARTITION p2025 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2026-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);

-- =============================================
-- 迁移完成后，执行以下步骤切换生产表：
-- 1. RENAME TABLE daily_kline TO daily_kline_old;
-- 2. RENAME TABLE daily_kline_v2 TO daily_kline;
-- 3. DROP TABLE daily_kline_old;
-- =============================================
