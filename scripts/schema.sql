-- Trading Buddy - 数据库初始化脚本
-- V1 版本：股票基础信息 + K线数据

-- 创建数据库
CREATE DATABASE IF NOT EXISTS trading CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE trading;

-- =============================================
-- 1. 股票基础信息表
-- =============================================
CREATE TABLE IF NOT EXISTS stock_info (
    code VARCHAR(20) PRIMARY KEY COMMENT '股票代码，如 000001.SZ',
    name VARCHAR(50) NOT NULL COMMENT '股票名称',
    ipo_date DATE COMMENT '上市日期',
    out_date DATE COMMENT '退市日期',
    stock_type ENUM('common', 'st', 'star', 'growth', 'beijing') DEFAULT 'common' COMMENT '股票类型',
    market ENUM('sh', 'sz', 'bj', 'hk', 'us') NOT NULL COMMENT '交易市场',
    industry VARCHAR(50) COMMENT '所属行业',
    sector_code VARCHAR(20) COMMENT '所属板块代码',
    is_trading TINYINT(1) DEFAULT 1 COMMENT '是否在交易',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_market (market),
    INDEX idx_industry (industry),
    INDEX idx_stock_type (stock_type),
    INDEX idx_is_trading (is_trading)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票基础信息';

-- =============================================
-- 2. 日线K线数据表
-- =============================================
CREATE TABLE IF NOT EXISTS daily_kline (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open DECIMAL(10, 2) NOT NULL COMMENT '开盘价',
    high DECIMAL(10, 2) NOT NULL COMMENT '最高价',
    low DECIMAL(10, 2) NOT NULL COMMENT '最低价',
    close DECIMAL(10, 2) NOT NULL COMMENT '收盘价',
    pre_close DECIMAL(10, 2) COMMENT '前一日收盘价',
    volume BIGINT COMMENT '成交量（股）',
    amount DECIMAL(20, 2) COMMENT '成交额（元）',
    turnover_rate DECIMAL(10, 4) COMMENT '换手率',
    adjust_flag VARCHAR(2) DEFAULT '3' COMMENT '复权类型: 1=后复权 2=前复权 3=不复权',
    
    -- 预计算字段（可选，后续使用）；列名与 ORM DailyKlineModel.change_pct 一致
    change DECIMAL(10, 2) COMMENT '涨跌额',
    change_pct DECIMAL(10, 4) COMMENT '涨跌幅%',
    ma5 DECIMAL(10, 2) COMMENT '5日均线',
    ma10 DECIMAL(10, 2) COMMENT '10日均线',
    ma20 DECIMAL(10, 2) COMMENT '20日均线',
    ma60 DECIMAL(10, 2) COMMENT '60日均线',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date_flag (code, trade_date, adjust_flag),
    INDEX idx_trade_date (trade_date),
    INDEX idx_code (code),
    INDEX ix_daily_kline_trade_date_pct (trade_date, change_pct),
    INDEX ix_daily_kline_trade_date_amount (trade_date, amount)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='日线K线数据';

-- =============================================
-- 3. 个股板块关联表
-- =============================================
CREATE TABLE IF NOT EXISTS stock_sector (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    sector_code VARCHAR(20) NOT NULL COMMENT '板块代码',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_sector (stock_code, sector_code),
    INDEX idx_sector_code (sector_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股板块关联';

-- =============================================
-- 4. 政策事件表
-- =============================================
CREATE TABLE IF NOT EXISTS policy_event (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sector_code VARCHAR(20) COMMENT '关联板块代码',
    title VARCHAR(200) NOT NULL COMMENT '事件标题',
    source VARCHAR(50) COMMENT '来源',
    event_date DATE COMMENT '事件日期',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sector_code (sector_code),
    INDEX idx_event_date (event_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='政策催化事件';

-- =============================================
-- 5. 分钟K线数据表（可选，后续扩展）
-- =============================================
CREATE TABLE IF NOT EXISTS minute_kline (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    trade_time DATETIME NOT NULL COMMENT '交易时间',
    period VARCHAR(10) NOT NULL COMMENT '周期: 1min/5min/15min/30min/60min',
    open DECIMAL(10, 2) NOT NULL COMMENT '开盘价',
    high DECIMAL(10, 2) NOT NULL COMMENT '最高价',
    low DECIMAL(10, 2) NOT NULL COMMENT '最低价',
    close DECIMAL(10, 2) NOT NULL COMMENT '收盘价',
    volume BIGINT COMMENT '成交量',
    amount DECIMAL(20, 2) COMMENT '成交额',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_time_period (code, trade_time, period),
    INDEX idx_trade_date (trade_date),
    INDEX idx_period (period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分钟K线数据';

-- =============================================
-- 4. 板块信息表
-- =============================================
CREATE TABLE IF NOT EXISTS sector_info (
    code VARCHAR(20) PRIMARY KEY COMMENT '板块代码',
    name VARCHAR(50) NOT NULL COMMENT '板块名称',
    sector_type ENUM('industry', 'concept') NOT NULL COMMENT '板块类型: industry=行业, concept=概念',
    stock_count INT DEFAULT 0 COMMENT '成分股数量',
    leading_stocks JSON COMMENT '龙头股代码列表',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sector_type (sector_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块信息';

-- =============================================
-- 5. 指数数据表（用于大盘行情）
-- =============================================
CREATE TABLE IF NOT EXISTS index_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL COMMENT '指数代码',
    name VARCHAR(50) NOT NULL COMMENT '指数名称',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open DECIMAL(10, 2) NOT NULL COMMENT '开盘点位',
    high DECIMAL(10, 2) NOT NULL COMMENT '最高点位',
    low DECIMAL(10, 2) NOT NULL COMMENT '最低点位',
    close DECIMAL(10, 2) NOT NULL COMMENT '收盘点位',
    volume BIGINT COMMENT '成交量',
    amount DECIMAL(20, 2) COMMENT '成交额',
    change DECIMAL(10, 2) COMMENT '涨跌点位',
    pct_change DECIMAL(10, 4) COMMENT '涨跌幅',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date (code, trade_date),
    INDEX idx_trade_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指数数据';

-- =============================================
-- 6. 数据更新日志表（用于追踪数据同步状态）
-- =============================================
CREATE TABLE IF NOT EXISTS sync_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(50) NOT NULL COMMENT '数据源: baostock/tushare',
    data_type VARCHAR(50) NOT NULL COMMENT '数据类型: stock_info/daily_kline/minute_kline',
    last_update DATE COMMENT '最后更新日期',
    status ENUM('success', 'failed', 'running') DEFAULT 'success' COMMENT '状态',
    records_count INT DEFAULT 0 COMMENT '更新记录数',
    error_message TEXT COMMENT '错误信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source (source),
    INDEX idx_data_type (data_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据同步日志';
