#!/bin/bash
# 快速切换 pal-mcp-server 使用的 Gemini/Codex 模型
# 用法: ./switch-model.sh [gemini|codex] [model-name]
# 示例:
#   ./switch-model.sh gemini gemini-2.5-pro
#   ./switch-model.sh gemini gemini-3-flash-preview
#   ./switch-model.sh codex o4-mini

set -e

PAL_SERVER_PATH="${PAL_MCP_SERVER_PATH:-/Users/panlingchuan/Downloads/My_Project/pal-mcp-server}"
CLI_CLIENTS_DIR="$PAL_SERVER_PATH/conf/cli_clients"

show_usage() {
    echo "切换 PAL MCP Server 使用的模型"
    echo ""
    echo "用法: $0 <cli> <model>"
    echo ""
    echo "CLI 选项:"
    echo "  gemini  - 切换 Gemini CLI 模型"
    echo "  codex   - 切换 Codex CLI 模型"
    echo ""
    echo "常用 Gemini 模型:"
    echo "  gemini-2.5-pro          - 高性能推理 (1M ctx)"
    echo "  gemini-2.5-flash        - 快速响应 (1M ctx)"
    echo "  gemini-3-flash-preview  - 最新预览版"
    echo "  gemini-3-pro-preview    - Pro 预览版"
    echo ""
    echo "常用 Codex 模型:"
    echo "  o4-mini   - 轻量版"
    echo "  o3        - 标准版"
    echo ""
    echo "示例:"
    echo "  $0 gemini gemini-2.5-pro"
    echo "  $0 codex o4-mini"
}

show_current() {
    echo "当前配置:"
    echo ""

    if [ -f "$CLI_CLIENTS_DIR/gemini.json" ]; then
        model=$(grep -o '"gemini[^"]*"' "$CLI_CLIENTS_DIR/gemini.json" | grep -v "gemini\"" | head -1 | tr -d '"')
        echo "  Gemini: $model"
    fi

    if [ -f "$CLI_CLIENTS_DIR/codex.json" ]; then
        # Codex 模型在 additional_args 之外，这里只显示配置文件存在
        echo "  Codex: (使用默认模型)"
    fi
}

switch_gemini_model() {
    local new_model="$1"
    local config_file="$CLI_CLIENTS_DIR/gemini.json"

    if [ ! -f "$config_file" ]; then
        echo "错误: 找不到 $config_file"
        exit 1
    fi

    # 备份原配置
    cp "$config_file" "$config_file.bak"

    # 使用 sed 替换模型名（macOS 兼容）
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/\"gemini-[^\"]*\"/\"$new_model\"/g" "$config_file"
    else
        sed -i "s/\"gemini-[^\"]*\"/\"$new_model\"/g" "$config_file"
    fi

    echo "Gemini 模型已切换为: $new_model"
    echo "需要重启 Claude Code 生效"
}

switch_codex_model() {
    local new_model="$1"
    echo "Codex 模型切换需要修改 Codex CLI 自身配置"
    echo "请运行: codex config set model $new_model"
}

# 主逻辑
case "${1:-}" in
    gemini)
        if [ -z "${2:-}" ]; then
            echo "错误: 请指定模型名"
            show_usage
            exit 1
        fi
        switch_gemini_model "$2"
        ;;
    codex)
        if [ -z "${2:-}" ]; then
            echo "错误: 请指定模型名"
            show_usage
            exit 1
        fi
        switch_codex_model "$2"
        ;;
    status|show|current)
        show_current
        ;;
    -h|--help|help)
        show_usage
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
