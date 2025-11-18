-- v0.2.1: 为 trades 表添加确认延迟追踪字段
-- 运行方式：sqlite3 data/portfolio.db < scripts/migrate_v0_2_1_add_delayed_tracking.sql

ALTER TABLE trades ADD COLUMN confirmation_status TEXT DEFAULT 'normal';
ALTER TABLE trades ADD COLUMN delayed_reason TEXT;
ALTER TABLE trades ADD COLUMN delayed_since DATE;

-- 为已确认的交易显式设置 confirmation_status
UPDATE trades
SET confirmation_status = 'normal'
WHERE status = 'confirmed';
