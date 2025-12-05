"""基金限购/暂停公告 Facts 模型（v0.4.4+ 规划）。

用途：
- 记录 QDII 限额、暂停申购等外部约束，供规则层和 AI 分析使用
- 为 DCA 事实快照提供"外部约束事实"输入，区分"被限额 vs 主动调整"
- 支持未来"定投执行异常检测"功能

设计原则：
- 规则层只记录"什么时候，这只基金被限额/暂停"，不做语义判断
- AI 基于这些事实判断：金额变化是限额导致还是主动调整
- 数据来源：手动录入 / 东方财富公告抓取 / 其他数据源

实现时机：
- v0.4.4：表结构设计 + 数据模型定义（本阶段，暂不实现 Repo）
- v0.4.5+：手动录入工具 + Repo 实现
- v0.5+：东方财富公告抓取自动化
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class FundRestrictionFact:
    """
    基金限购/暂停公告事实记录（*Fact 规范）。

    规则层只记录"什么时候，这只基金被限额/暂停"，不做语义判断。
    AI 基于这些事实判断：
    - 金额变化是限额导致还是主动调整
    - 间隔异常是暂停申购还是用户主动跳过
    - DCA 执行率下降的原因是外部约束还是策略变化

    字段说明：
    - fund_code: 基金代码
    - start_date: 限制开始日期
    - end_date: 限制结束日期（None=仍在限制中）
    - restriction_type: 限制类型（daily_limit / suspend / resume）
    - limit_amount: 限购金额（仅 daily_limit 时有值）
    - source: 数据来源（eastmoney / manual / other）
    - source_url: 公告链接（可选）
    - note: 公告摘要或补充说明（可选）

    restriction_type 枚举：
    - daily_limit: 每日限购（如 QDII 额度紧张，每日只能买 10 元）
    - suspend: 暂停申购
    - resume: 恢复申购（显式标记恢复时间点）
    """

    fund_code: str
    """基金代码。"""

    start_date: date
    """限制开始日期。"""

    end_date: date | None
    """限制结束日期（None=仍在限制中）。"""

    restriction_type: str
    """限制类型：daily_limit / suspend / resume。"""

    limit_amount: Decimal | None = None
    """限购金额（仅 daily_limit 时有值，如 Decimal('10.00')）。"""

    source: str = "manual"
    """数据来源：eastmoney / manual / other。"""

    source_url: str | None = None
    """公告链接（可选）。"""

    note: str | None = None
    """公告摘要或补充说明（可选）。"""

    def is_active_on(self, check_date: date) -> bool:
        """
        检查指定日期是否在限制期内。

        Args:
            check_date: 需要检查的日期。

        Returns:
            True 如果限制在该日期有效，否则 False。

        示例：
            >>> fact = FundRestrictionFact(
            ...     fund_code="008971",
            ...     start_date=date(2025, 11, 1),
            ...     end_date=None,
            ...     restriction_type="daily_limit",
            ...     limit_amount=Decimal("10.00")
            ... )
            >>> fact.is_active_on(date(2025, 11, 15))
            True
            >>> fact.is_active_on(date(2025, 10, 31))
            False
        """
        if check_date < self.start_date:
            return False
        if self.end_date is None:
            return True  # 仍在限制中
        return check_date <= self.end_date

    @property
    def is_currently_active(self) -> bool:
        """
        检查限制是否仍在生效中（end_date 为 None）。

        Returns:
            True 如果限制仍在生效（end_date 为 None），否则 False。
        """
        return self.end_date is None

    @property
    def duration_days(self) -> int | None:
        """
        计算限制持续天数。

        Returns:
            限制持续天数（start_date 到 end_date 的天数差）。
            如果 end_date 为 None，返回 None。
        """
        if self.end_date is None:
            return None
        return (self.end_date - self.start_date).days
