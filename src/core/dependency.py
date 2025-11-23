"""
依赖注入装饰器（Dependency Injection）。

职责：
- 提供类似 FastAPI `Depends()` 的自动依赖注入机制
- 通过装饰器自动填充函数的可选参数
- 支持测试时手动传入 Mock 对象覆盖默认依赖

设计原则：
- 显式注册：所有可注入依赖必须通过 @register 显式注册
- 命名一致：注册名必须与函数参数名完全一致
- 可覆盖：调用时传入的非 None 参数不会被覆盖

使用示例：
    # 1. 注册依赖工厂（在 src/core/container.py 中）
    @register("trade_repo")
    def get_trade_repo():
        return TradeRepo(get_db_connection())

    # 2. 在 Flow 函数上使用装饰器
    @dependency
    def confirm_trades(
        *,
        today: date,
        trade_repo: TradeRepo | None = None,  # 自动注入
        nav_service: LocalNavService | None = None,  # 自动注入
    ) -> ConfirmResult:
        # trade_repo 和 nav_service 已自动填充，直接使用
        to_confirm = trade_repo.list_pending_to_confirm(today)
        ...

    # 3. 调用（依赖自动创建）
    result = confirm_trades(today=date.today())

    # 4. 测试时覆盖依赖
    result = confirm_trades(
        today=date.today(),
        trade_repo=MockTradeRepo(),  # 手动传入，不会被覆盖
    )

注意事项：
- 注册名必须与函数参数名完全一致（大小写敏感）
- 仅当参数值为 None 时才会自动注入
- IDE 可能无法推断注入后的类型，但运行时保证正确
- 依赖注册在 src/flows/__init__.py 自动触发（导入任何 flow 模块时生效）
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, TypeVar

# ========== 全局注册表 ==========

# 依赖注册表：参数名 -> 工厂函数
# 例如：{"trade_repo": get_trade_repo, "nav_service": get_local_nav_service}
_REGISTRY: dict[str, Callable[[], Any]] = {}

T = TypeVar("T")


def register(name: str) -> Callable[[Callable[[], T]], Callable[[], T]]:
    """
    装饰器：将工厂函数注册到依赖注入容器。

    Args:
        name: 注册名称，必须与目标函数的参数名完全一致。

    Returns:
        装饰器函数。

    示例：
        @register("trade_repo")
        def get_trade_repo() -> TradeRepo:
            conn = get_db_connection()
            calendar = get_calendar_service()
            return TradeRepo(conn, calendar)

        # 现在 "trade_repo" 参数可以被自动注入
    """

    def decorator(factory_func: Callable[[], T]) -> Callable[[], T]:
        _REGISTRY[name] = factory_func
        return factory_func

    return decorator


def dependency(func: Callable[..., T]) -> Callable[..., T]:
    """
    依赖注入装饰器：自动注入函数的可选参数。

    工作原理：
    1. 检查函数签名，找出所有参数
    2. 对于每个参数：
       - 如果调用时未传值（或传入 None）
       - 且该参数名在注册表中存在
       - 则调用对应的工厂函数创建实例并注入
    3. 如果调用时传入了非 None 值，则保持原值不覆盖

    Args:
        func: 需要自动注入依赖的函数。

    Returns:
        包装后的函数。

    示例：
        @dependency
        def confirm_trades(
            *,
            today: date,
            trade_repo: TradeRepo | None = None,
            nav_service: LocalNavService | None = None,
        ) -> ConfirmResult:
            # trade_repo 和 nav_service 自动注入
            ...

        # 调用方式 1：依赖自动创建
        result = confirm_trades(today=date.today())

        # 调用方式 2：手动传入（测试场景）
        result = confirm_trades(
            today=date.today(),
            trade_repo=MockTradeRepo(),
        )

    注意：
        - 参数名必须与注册表中的名字完全一致
        - 仅当参数为 None 时才会注入
        - 使用反射会有轻微性能开销（通常可忽略）
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        # 获取函数签名
        sig = inspect.signature(func)

        # 绑定已传入的参数
        bound_args = sig.bind_partial(*args, **kwargs)
        bound_args.apply_defaults()

        # 遍历所有参数，检查是否需要注入
        for param_name, param in sig.parameters.items():
            # 检查该参数是否需要注入：
            # 1. 参数名在注册表中
            # 2. 且当前值为 None（未传入或显式传入 None）
            if param_name in _REGISTRY:
                current_value = bound_args.arguments.get(param_name)
                if current_value is None:
                    # 🔥 核心魔法：调用工厂函数创建实例
                    kwargs[param_name] = _REGISTRY[param_name]()

        return func(*args, **kwargs)

    return wrapper


def get_registered_deps() -> dict[str, Callable[[], Any]]:
    """
    获取当前注册的所有依赖（用于调试）。

    Returns:
        依赖注册表的副本。

    示例：
        deps = get_registered_deps()
        print(f"已注册 {len(deps)} 个依赖：{list(deps.keys())}")
    """
    return _REGISTRY.copy()
