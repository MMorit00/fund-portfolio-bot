#!/bin/bash
# 检查 Gemini 和 Codex CLI 是否可用
# 用法: ./check-cli-health.sh [gemini|codex|all]

set -e

check_gemini() {
    if command -v gemini &> /dev/null; then
        echo "gemini:available"
        return 0
    else
        echo "gemini:unavailable"
        return 1
    fi
}

check_codex() {
    if command -v codex &> /dev/null; then
        echo "codex:available"
        return 0
    else
        echo "codex:unavailable"
        return 1
    fi
}

case "${1:-all}" in
    gemini)
        check_gemini
        ;;
    codex)
        check_codex
        ;;
    all)
        gemini_status=0
        codex_status=0
        check_gemini || gemini_status=1
        check_codex || codex_status=1

        if [ $gemini_status -eq 0 ] && [ $codex_status -eq 0 ]; then
            echo "status:all_available"
            exit 0
        elif [ $gemini_status -eq 0 ] || [ $codex_status -eq 0 ]; then
            echo "status:partial"
            exit 0
        else
            echo "status:none_available"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 [gemini|codex|all]"
        exit 1
        ;;
esac
