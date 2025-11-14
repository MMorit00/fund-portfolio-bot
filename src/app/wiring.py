from __future__ import annotations

"""
依赖装配（wiring）。

MVP 阶段先留占位：未来在此绑定 Protocol -> Adapter 实现，
供 jobs/* 与 bot/cli 入口注入 UseCase 所需依赖。
"""

from src.usecases.trading.create_trade import CreateTrade


def get_create_trade_usecase() -> CreateTrade:
    # TODO: 实例化具体仓储与适配器，然后注入 CreateTrade
    raise NotImplementedError

