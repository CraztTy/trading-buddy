-- MySQL: 为 daily_kline 表添加 pre_close 列（若不存在）
ALTER TABLE daily_kline
ADD COLUMN IF NOT EXISTS pre_close DECIMAL(10, 2) COMMENT '前收盘价';
