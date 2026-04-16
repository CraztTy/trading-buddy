-- SQLite: 为 daily_kline 表添加 pre_close 列（若不存在）
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;

-- 仅当列不存在时添加
SELECT CASE
    WHEN NOT EXISTS(
        SELECT 1 FROM pragma_table_info('daily_kline') WHERE name = 'pre_close'
    )
    THEN
        ALTER TABLE daily_kline ADD COLUMN pre_close REAL;
    END;

COMMIT;
PRAGMA foreign_keys=ON;
