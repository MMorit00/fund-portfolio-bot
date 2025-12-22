#!/usr/bin/env python3
"""
从 clink MCP 返回的 JSON 中提取核心内容。
过滤掉所有 metadata，只保留 content 字段。

用法:
    echo '{"status":"success","content":"Hello","metadata":{...}}' | python extract-content.py
    python extract-content.py < response.json
"""

import json
import sys


def extract_content(json_str: str) -> str:
    """从 clink 响应中提取 content 字段。"""
    try:
        data = json.loads(json_str)

        # 直接返回 content
        if isinstance(data, dict):
            content = data.get("content", "")
            if content:
                return content

            # 如果是嵌套结构，尝试提取
            if "result" in data:
                result = data["result"]
                if isinstance(result, dict):
                    return result.get("content", str(result))
                return str(result)

        return json_str
    except json.JSONDecodeError:
        # 不是 JSON，直接返回原文
        return json_str


def main():
    input_text = sys.stdin.read().strip()
    if not input_text:
        sys.exit(0)

    content = extract_content(input_text)
    print(content)


if __name__ == "__main__":
    main()
