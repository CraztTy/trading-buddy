#!/usr/bin/env bash
# Trading Buddy - 复权档分批拉取脚本
# 每 BATCH_SIZE 只股票重启一次进程，避免 baostock 连接长期运行后僵死

set -euo pipefail

BATCH_SIZE=50
TOTAL_CODES=4733
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# 计算需要多少批
BATCH_COUNT=$(( (TOTAL_CODES + BATCH_SIZE - 1) / BATCH_SIZE ))

echo "========================================"
echo "复权档分批拉取: adjust_flags 1 (后复权) + 2 (前复权)"
echo "每批 ${BATCH_SIZE} 只, 共 ${BATCH_COUNT} 批, 总计 ${TOTAL_CODES} 只"
echo "========================================"

for (( i=0; i<BATCH_COUNT; i++ )); do
    OFFSET=$(( i * BATCH_SIZE ))
    LOG_FILE="${LOG_DIR}/fetch_flag12_batch_${i}_offset_${OFFSET}.log"

    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 第 $((i+1))/${BATCH_COUNT} 批: offset=${OFFSET}, limit=${BATCH_SIZE} ==="

    python scripts/fetch_data.py \
        --mode all \
        --adjust-flags 1 2 \
        --skip "$OFFSET" \
        --limit "$BATCH_SIZE" \
        > "$LOG_FILE" 2>&1

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 第 $((i+1))/${BATCH_COUNT} 批完成 ==="

    # 如果不是最后一批，休息几秒让 baostock 连接彻底释放
    if (( i < BATCH_COUNT - 1 )); then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 休息 5 秒后启动下一批..."
        sleep 5
    fi
done

echo ""
echo "========================================"
echo "全部 ${BATCH_COUNT} 批完成!"
echo "========================================"
