"""Broker 适配器工厂 — 根据 adapter_type 创建对应适配器实例。"""

from __future__ import annotations

from src.broker.base import BaseBrokerAdapter
from src.broker.paper_adapter import PaperBrokerAdapter


class BrokerAdapterFactory:
    """BrokerAdapter 工厂。

    用法:
        adapter = BrokerAdapterFactory.create(
            "paper",
            session=session,
            user_id=user_id,
            account_label="default",
        )
        adapter = BrokerAdapterFactory.create(
            "xtquant",
            account_id="123456",
            qmt_path=r"C:\\国金QMT交易端\\userdata_mini",
            session_id=123456,
        )
    """

    _ADAPTERS: dict[str, type[BaseBrokerAdapter]] = {
        "paper": PaperBrokerAdapter,
    }

    @classmethod
    def register(cls, name: str, adapter_class: type[BaseBrokerAdapter]) -> None:
        """注册新的适配器类型。"""
        cls._ADAPTERS[name] = adapter_class

    @classmethod
    def create(cls, adapter_type: str, **kwargs) -> BaseBrokerAdapter:
        """创建指定类型的 BrokerAdapter 实例。

        Args:
            adapter_type: 适配器类型，如 "paper"、"xtquant"
            **kwargs: 传递给适配器构造函数的参数

        Raises:
            ValueError: 未知的适配器类型
        """
        adapter_type = adapter_type.strip().lower()

        # xtquant 延迟导入，避免未安装时直接报错
        if adapter_type == "xtquant":
            from src.broker.xtquant_adapter import XtquantBrokerAdapter

            cls._ADAPTERS["xtquant"] = XtquantBrokerAdapter

        adapter_class = cls._ADAPTERS.get(adapter_type)
        if adapter_class is None:
            known = ", ".join(sorted(cls._ADAPTERS.keys()))
            raise ValueError(f"未知的 broker adapter: '{adapter_type}'。已知: {known}")

        return adapter_class(**kwargs)

    @classmethod
    def available_types(cls) -> list[str]:
        """返回已注册的适配器类型列表。"""
        return sorted(cls._ADAPTERS.keys())
