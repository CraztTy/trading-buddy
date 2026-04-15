-- MySQL 迁移脚本：为 daily_kline 增加 adjust_flag 列并更新唯一约束
-- 适用场景：已有生产数据的 MySQL 库，需在维护窗口执行

ALTER TABLE daily_kline
    ADD COLUMN IF NOT EXISTS adjust_flag VARCHAR(2) NOT NULL DEFAULT '3' COMMENT '复权类型: 1=后复权 2=前复权 3=不复权';

-- 更新旧数据（若之前已存在 adjust_flag 列但可能为 NULL）
UPDATE daily_kline SET adjust_flag = '3' WHERE adjust_flag IS NULL OR adjust_flag = '';

-- 删除旧唯一键，添加包含 adjust_flag 的新唯一键
ALTER TABLE daily_kline
    DROP INDEX IF EXISTS uk_code_date,
    ADD UNIQUE KEY uk_code_date_flag (code, trade_date, adjust_flag);
