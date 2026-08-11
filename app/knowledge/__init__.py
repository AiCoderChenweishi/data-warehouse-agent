"""数仓知识库 + 决策引擎 (Data Warehouse Knowledge Base)

本包把 Kimball《数据仓库工具箱》和阿里《OneData》方法论
编码为可被程序调用的 Python 决策引擎,服务于:
    - SQL 生成器(后续 backend 层)
    - Web UI(后续 frontend 层)
    - 单元测试(本包自带的 pytest 套件)

模块清单 (Modules):
    kimball    - Kimball 4 步法决策树 (业务过程 / 粒度 / 维度 / 事实 / 事实表类型)
    onedata    - 阿里 OneData 规范 (数据域 / 总线矩阵 / 分层 / 命名 / 指标)
    dimensions - 维度高级主题 (SCD / 拉链 / 退化 / 杂项 / 微型 / 多值 / 递归)
    facts      - 事实表设计 (事务 / 周期快照 / 累积 / 聚集 / 不可加拆分)
    prompts    - 7 阶段引导式问答模板 (业务调研 → 测试验证)

调用示例 (Quick Start):
    >>> from app.knowledge import kimball, onedata, dimensions, facts, prompts
    >>> procs = kimball.identify_business_process("用户在下单后,会经历支付、发货、收货")
    >>> len(procs) >= 3
    True
    >>> table = onedata.generate_naming('dws', 'trade', 'order', 'pay', '1d')
    >>> table
    'dws_trade_order_pay_1d'
    >>> scd = dimensions.recommend_scd_type("用户地址", "high", need_history=True)
    >>> scd['scd_type']
    2
    >>> fact = facts.decompose_non_additive_fact("客单价", "GMV / 订单数")
    >>> fact['numerator']
    'GMV'
    >>> stage0 = prompts.get_stage(0)
    >>> stage0['name']
    '业务调研'

来源 (Sources):
    - Kimball "The Data Warehouse Toolkit" (3rd Edition, 2013)
    - 阿里《OneData — 大数据之路》(2017)
    - Data Vault 2.0 实施方法论
"""

from . import kimball
from . import onedata
from . import dimensions
from . import facts
from . import prompts

__all__ = [
    "kimball",
    "onedata",
    "dimensions",
    "facts",
    "prompts",
]

__version__ = "0.1.0"
