#!/bin/bash
# 检查 PAL MCP Server 状态和配置
# 用法: ./pal-status.sh

set -e

PAL_SERVER_PATH="${PAL_MCP_SERVER_PATH:-/Users/panlingchuan/Downloads/My_Project/pal-mcp-server}"

echo "=== PAL MCP Server 状态 ==="
echo ""

# 检查服务器路径
if [ -d "$PAL_SERVER_PATH" ]; then
    echo "服务器路径: $PAL_SERVER_PATH"
else
    echo "错误: 找不到服务器路径 $PAL_SERVER_PATH"
    exit 1
fi

# 检查版本
if [ -f "$PAL_SERVER_PATH/config.py" ]; then
    version=$(grep -o '__version__ = "[^"]*"' "$PAL_SERVER_PATH/config.py" | cut -d'"' -f2)
    echo "版本: $version"
fi

echo ""
echo "=== CLI 客户端配置 ==="

# Gemini 配置
if [ -f "$PAL_SERVER_PATH/conf/cli_clients/gemini.json" ]; then
    echo ""
    echo "Gemini:"
    cat "$PAL_SERVER_PATH/conf/cli_clients/gemini.json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
args = data.get('additional_args', [])
model = next((a for a in args if a.startswith('gemini-')), 'unknown')
print(f'  模型: {model}')
print(f'  额外参数: {\" \".join(args[:2])}...')
roles = list(data.get('roles', {}).keys())
print(f'  角色: {roles}')
" 2>/dev/null || echo "  (解析失败)"
fi

# Codex 配置
if [ -f "$PAL_SERVER_PATH/conf/cli_clients/codex.json" ]; then
    echo ""
    echo "Codex:"
    cat "$PAL_SERVER_PATH/conf/cli_clients/codex.json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
args = data.get('additional_args', [])
print(f'  额外参数: {\" \".join(args[:3])}...')
roles = list(data.get('roles', {}).keys())
print(f'  角色: {roles}')
" 2>/dev/null || echo "  (解析失败)"
fi

# Claude 配置
if [ -f "$PAL_SERVER_PATH/conf/cli_clients/claude.json" ]; then
    echo ""
    echo "Claude:"
    cat "$PAL_SERVER_PATH/conf/cli_clients/claude.json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
roles = list(data.get('roles', {}).keys())
print(f'  角色: {roles}')
" 2>/dev/null || echo "  (解析失败)"
fi

echo ""
echo "=== CLI 可用性 ==="

# 检查 CLI 命令
for cli in gemini codex claude; do
    if command -v $cli &> /dev/null; then
        echo "  $cli: 可用"
    else
        echo "  $cli: 未安装"
    fi
done

echo ""
echo "=== 环境变量 ==="
echo "  DEFAULT_MODEL: ${DEFAULT_MODEL:-auto}"
echo "  MAX_MCP_OUTPUT_TOKENS: ${MAX_MCP_OUTPUT_TOKENS:-未设置}"
echo "  LOCALE: ${LOCALE:-未设置}"
