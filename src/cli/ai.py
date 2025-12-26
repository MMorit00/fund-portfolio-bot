"""
AI 分析 CLI 入口。

职责：
- 提供自然语言查询入口
- 渲染 AI 响应（Rich 美化输出）
- 处理错误和降级显示

使用方式：
    uv run python -m src.cli.ai "天弘余额宝最近的定投情况如何？"
    uv run python -m src.cli.ai --hello  # 验证 AI 连接
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# 加载 .env 文件
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv 未安装，跳过

# 导入 tools 模块以触发工具注册
from src.ai import tools  # noqa: F401
from src.ai.client import AIClient
from src.ai.schemas.responses import FinancialAnalysis

console = Console()
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="AI 投资分析助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  uv run python -m src.cli.ai "天弘余额宝最近的定投情况如何？"
  uv run python -m src.cli.ai "查询基金 000001 的净值"
  uv run python -m src.cli.ai --hello  # 验证 AI 连接
        """,
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="自然语言查询",
    )
    parser.add_argument(
        "--hello",
        action="store_true",
        help="验证 AI 连接（简单问候）",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="输出原始 JSON（不渲染）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试日志",
    )
    return parser.parse_args()


def _render_response(json_str: str) -> None:
    """
    渲染 AI 响应。

    Args:
        json_str: AI 返回的 JSON 字符串。

    行为：
    - 尝试解析为 FinancialAnalysis 结构
    - 成功则渲染为 Rich Panel
    - 失败则降级显示原始文本
    """
    try:
        # 1. 尝试解析为结构化响应
        data = FinancialAnalysis.model_validate_json(json_str)

        # 2. 渲染风险徽章
        risk_colors = {"low": "green", "medium": "yellow", "high": "red"}
        risk_color = risk_colors.get(data.risk_level, "white")
        risk_badge = f"[{risk_color}]Risk: {data.risk_level.upper()}[/]"

        # 3. 组合 Markdown 内容
        content = f"""
### 概览
{data.summary}

### 深度分析
{data.analysis}

### 建议
{data.advice}
"""

        # 4. 缺失数据提示
        if data.missing_data:
            missing = ", ".join(data.missing_data)
            content += f"\n\n*缺失数据: {missing}*"

        # 5. 渲染 Panel
        console.print(
            Panel(
                Markdown(content),
                title=f"AI 投资分析  |  {risk_badge}",
                border_style="blue",
            )
        )

    except Exception:
        # 降级：尝试解析为普通 JSON
        try:
            data = json.loads(json_str)
            console.print(Panel(json.dumps(data, ensure_ascii=False, indent=2), title="AI 响应"))
        except json.JSONDecodeError:
            # 最终降级：显示原始文本
            console.print(Panel(json_str, title="AI 响应（原始）"))


def _do_hello() -> int:
    """
    验证 AI 连接。

    Returns:
        0=成功，1=失败。
    """
    console.print("[dim]正在验证 AI 连接...[/dim]")

    try:
        client = AIClient()
        response = client.simple_chat("你好，请用一句话介绍自己")

        console.print(f"[green]AI 响应:[/green] {response}")
        console.print("[green]✓ AI 连接验证成功[/green]")
        return 0

    except ValueError as e:
        console.print(f"[red]✗ 配置错误: {e}[/red]")
        console.print("[dim]请检查 LLM_API_KEY 环境变量[/dim]")
        return 1
    except Exception as e:
        console.print(f"[red]✗ 连接失败: {e}[/red]")
        return 1


def _do_query(query: str, raw: bool = False) -> int:
    """
    执行 AI 查询。

    Args:
        query: 用户查询。
        raw: 是否输出原始 JSON。

    Returns:
        0=成功，1=失败。
    """
    try:
        client = AIClient()
        console.print(f"[dim]正在分析: {query}[/dim]")

        response = client.chat(query)

        if raw:
            console.print(response)
        else:
            _render_response(response)

        return 0

    except ValueError as e:
        console.print(f"[red]✗ 配置错误: {e}[/red]")
        console.print("[dim]请检查 LLM_API_KEY 环境变量[/dim]")
        return 1
    except Exception as e:
        logger.exception("[AIClient] 查询失败")
        console.print(f"[red]✗ 查询失败: {e}[/red]")
        return 1


def main() -> int:
    """CLI 主入口。"""
    args = _parse_args()

    # 配置日志
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    # 执行命令
    if args.hello:
        return _do_hello()

    if not args.query:
        console.print("[yellow]请输入查询内容，或使用 --hello 验证连接[/yellow]")
        console.print("[dim]示例: uv run python -m src.cli.ai \"天弘余额宝最近的定投情况如何？\"[/dim]")
        return 1

    return _do_query(args.query, raw=args.raw)


if __name__ == "__main__":
    sys.exit(main())
