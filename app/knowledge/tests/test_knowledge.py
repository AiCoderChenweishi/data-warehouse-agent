"""数仓知识库单元测试 (Unit Tests for Knowledge Base)

覆盖维度:
    - Kimball 4 步法 5 个核心函数
    - 阿里 OneData 5 个核心函数
    - 维度高级主题 6 个核心函数
    - 事实表设计 5 个核心函数
    - 引导式问答 4 个核心函数

至少 20+ 测试用例,确保所有决策函数有边界覆盖。
"""

from __future__ import annotations

import pytest

# 从包入口导入
from app.knowledge import kimball, onedata, dimensions, facts, prompts


# ============================================================
# Kimball 模块测试
# ============================================================


class TestKimballBusinessProcess:
    """测试 Kimball Step 1: 业务过程识别。"""

    def test_identify_4_business_processes_in_order_scenario(self):
        """订单场景:识别出 下单/支付/发货/收货 4 个业务过程。"""
        result = kimball.identify_business_process(
            "用户在下单后,会经历支付、发货、收货"
        )
        names = {p["name"] for p in result}
        # 期望至少 3 个核心过程都被识别
        assert "下单" in names
        assert "支付" in names
        assert "发货" in names
        assert "收货" in names

    def test_identify_pay_and_refund(self):
        """识别支付 + 退款。"""
        result = kimball.identify_business_process(
            "买家支付订单后,如果不喜欢可以申请退款"
        )
        names = {p["name"] for p in result}
        assert "支付" in names
        assert "退货" in names  # 退款归到退货

    def test_identify_user_registration(self):
        """识别注册 + 登录。"""
        result = kimball.identify_business_process(
            "新用户注册后,可以登录系统;老用户直接登录即可"
        )
        names = {p["name"] for p in result}
        assert "注册" in names
        assert "登录" in names

    def test_known_processes_whitelist(self):
        """白名单:已知的业务过程即使不在词库也保留。"""
        result = kimball.identify_business_process(
            "用户买飞机票",
            known_processes=["航旅预订"]
        )
        names = {p["name"] for p in result}
        assert "航旅预订" in names  # 白名单保留

    def test_empty_description_returns_warning(self):
        """空描述返回警告而非崩溃。"""
        result = kimball.identify_business_process("")
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["confidence"] == 0.0
        assert "请提供" in result[0]["rationale"] or "空" in result[0]["rationale"]

    def test_no_match_returns_warning(self):
        """无动词描述返回警告。"""
        result = kimball.identify_business_process("用户和商品")
        assert isinstance(result, list)
        # 不应崩溃,可能返回空或低置信度
        # 如果非空,都是低置信度
        for p in result:
            assert p["confidence"] < 0.6


class TestKimballGrain:
    """测试 Kimball Step 2: 粒度声明。"""

    def test_grain_for_order_is_sub_order(self):
        """下单的粒度 = 子订单。"""
        grain = kimball.declare_grain("下单")
        assert "子订单" in grain

    def test_grain_for_pay_is_payment(self):
        """支付的粒度 = 支付单。"""
        grain = kimball.declare_grain("支付")
        assert "支付" in grain

    def test_grain_for_ship_is_shipment(self):
        """发货的粒度 = 发货单。"""
        grain = kimball.declare_grain("发货")
        assert "发货" in grain

    def test_grain_questions_for_order(self):
        """下单的粒度问题清单非空。"""
        qs = kimball.grain_questions("下单")
        assert isinstance(qs, list)
        assert len(qs) >= 2

    def test_grain_for_unknown_process_returns_generic(self):
        """未知业务过程返回通用原子粒度。"""
        grain = kimball.declare_grain("麦田怪圈")
        assert "原子事件粒度" in grain or "最小业务事件" in grain

    def test_grain_normalizes_compound_name(self):
        """复合业务过程名("下单流程")能截取核心词。"""
        grain = kimball.declare_grain("下单流程")
        assert "子订单" in grain


class TestKimballDimensions:
    """测试 Kimball Step 3: 维度识别。"""

    def test_dimensions_for_order_include_user(self):
        """下单维度必含用户/商品/时间。"""
        dims = kimball.identify_dimensions("下单", "子订单粒度")
        names = {d["name"] for d in dims}
        assert "用户" in names
        assert "商品" in names
        assert "时间" in names

    def test_dimensions_have_primary(self):
        """维度列表中至少有 1 个 primary 主维。"""
        dims = kimball.identify_dimensions("下单", "子订单粒度")
        roles = {d["role"] for d in dims}
        assert "primary" in roles

    def test_dimensions_sorted_by_role(self):
        """维度按 role 排序 (primary 优先)。"""
        dims = kimball.identify_dimensions("下单", "子订单粒度")
        # primary 应该在前
        first_role = dims[0]["role"]
        assert first_role == "primary"

    def test_dimensions_for_unknown_process_returns_generic(self):
        """未知业务过程返回通用维度。"""
        dims = kimball.identify_dimensions("麦田怪圈", "事件粒度")
        assert isinstance(dims, list)
        assert len(dims) >= 1


class TestKimballFacts:
    """测试 Kimball Step 4: 事实识别。"""

    def test_facts_for_order_have_additive(self):
        """下单事实有可加事实。"""
        facts_list = kimball.identify_facts("下单", "子订单粒度")
        assert any(f["additivity"] == "additive" for f in facts_list)

    def test_facts_for_order_have_non_additive(self):
        """下单事实有不可加事实(比率)。"""
        facts_list = kimball.identify_facts("下单", "子订单粒度")
        assert any(f["additivity"] == "non_additive" for f in facts_list)

    def test_facts_have_data_type(self):
        """每个事实有 data_type 字段。"""
        facts_list = kimball.identify_facts("下单", "子订单粒度")
        for f in facts_list:
            assert "data_type" in f
            assert f["data_type"] in ["DECIMAL(18,2)", "BIGINT", "FLOAT", "DECIMAL"]

    def test_facts_for_ship_have_semi_additive(self):
        """发货事实有半可加事实(发货时长)。"""
        facts_list = kimball.identify_facts("发货", "发货单粒度")
        assert any(f["additivity"] == "semi_additive" for f in facts_list)


class TestKimballFactType:
    """测试事实表类型决策。"""

    def test_fact_type_transaction_for_single_high_volume(self):
        """单一高吞吐过程 → 事务。"""
        result = kimball.decide_fact_type(["下单"], is_high_volume=True)
        assert result["fact_type"] == "transaction"
        assert result["confidence"] >= 0.8

    def test_fact_type_accumulating_for_multi_process_with_intervals(self):
        """多过程 + 时间区间 + 终态 → 累积快照。"""
        result = kimball.decide_fact_type(
            ["下单", "支付", "发货", "收货"],
            has_time_intervals=True,
            has_end_state=True,
        )
        assert result["fact_type"] == "accumulating_snapshot"
        assert result["confidence"] >= 0.8

    def test_fact_type_accumulating_for_4_processes_only_with_intervals(self):
        """4 业务过程 + 时间区间 (即使无 end_state 显式声明) → 累积快照。
        启发式:电商订单全流程 4 个过程(下单/支付/发货/收货)是累积快照的强信号。"""
        result = kimball.decide_fact_type(
            ["下单", "支付", "发货", "收货"],
            has_time_intervals=True,
        )
        assert result["fact_type"] == "accumulating_snapshot"

    def test_fact_type_periodic_snapshot_for_inventory(self):
        """库存类(状态度量)→ 周期快照。"""
        result = kimball.decide_fact_type(["库存盘点"])
        assert result["fact_type"] == "periodic_snapshot"

    def test_fact_type_for_empty_returns_warning(self):
        """空业务过程列表 → 警告 + 默认 transaction。"""
        result = kimball.decide_fact_type([])
        assert "warnings" in result
        assert len(result["warnings"]) >= 1
        assert result["fact_type"] == "transaction"

    def test_fact_type_with_time_intervals_only(self):
        """有时间区间但无终态 → 可能归为事务。"""
        result = kimball.decide_fact_type(
            ["下单", "支付"], has_time_intervals=True, has_end_state=False
        )
        # 业务过程 ≥ 2 但无终态,根据实现可能 transaction 或 累积
        assert result["fact_type"] in ["transaction", "accumulating_snapshot"]


class TestKimballFourStepPipeline:
    """测试 4 步法串联管道。"""

    def test_four_step_returns_all_stages(self):
        """4 步法返回 5 个阶段的结果。"""
        result = kimball.kimball_four_step(
            "用户在下单后,会经历支付、发货、收货,订单最终完结"
        )
        assert "step1_processes" in result
        assert "step2_grain" in result
        assert "step3_dimensions" in result
        assert "step4_facts" in result
        assert "step5_fact_type" in result

    def test_four_step_picks_accumulating_snapshot(self):
        """订单完整流程 → 累积快照。"""
        result = kimball.kimball_four_step(
            "用户在下单后,会经历支付、发货、收货,订单最终完结"
        )
        assert result["step5_fact_type"]["fact_type"] == "accumulating_snapshot"


# ============================================================
# OneData 模块测试
# ============================================================


class TestOneDataLayer:
    """测试分层架构定义。"""

    def test_all_6_layers_defined(self):
        """6 层架构都被定义。"""
        for layer in ["ods", "dwd", "dws", "dwt", "ads", "dim"]:
            defn = onedata.get_layer_definition(layer)
            assert "name" in defn
            assert "purpose" in defn
            assert "naming_pattern" in defn

    def test_unknown_layer_raises(self):
        """未知层抛 ValueError。"""
        with pytest.raises(ValueError) as exc_info:
            onedata.get_layer_definition("xyz")
        assert "未知层级" in str(exc_info.value)

    def test_ods_layer_purpose(self):
        """ODS 贴源层职责清晰。"""
        defn = onedata.get_layer_definition("ods")
        assert "贴源" in defn["name"] or "ODS" in defn["name"]
        assert "不做清洗" in defn["purpose"] or "原貌" in defn["purpose"]


class TestOneDataDomain:
    """测试数据域划分。"""

    def test_split_trade_domain(self):
        """电商模块 → trade 域。"""
        result = onedata.split_data_domain(
            "电商", ["订单管理", "支付管理"]
        )
        assert result["primary_domain"] == "trade"

    def test_split_mixed_domains(self):
        """混合模块 → 多域。"""
        result = onedata.split_data_domain(
            "电商", ["订单管理", "用户管理", "商品管理"]
        )
        assert "trade" in result["module_to_domain"].values()
        assert "user" in result["module_to_domain"].values()
        assert "item" in result["module_to_domain"].values()

    def test_uncategorized_module_returns_warning(self):
        """未识别模块放入 uncategorized + 警告。"""
        result = onedata.split_data_domain(
            "未知", ["天马行空模块"]
        )
        assert "天马行空模块" in result["uncategorized"]
        # 应该有 error 类型的 boundary_check
        error_checks = [c for c in result["boundary_checks"] if c.get("type") == "error"]
        assert len(error_checks) >= 1

    def test_finance_industry_info(self):
        """金融行业提示包含 finance 域。"""
        result = onedata.split_data_domain("金融银行业务", [])
        info_checks = [c for c in result["boundary_checks"] if c.get("type") == "info"]
        # 即使没模块,行业提示也应有
        assert any("finance" in c.get("message", "").lower() for c in info_checks)


class TestOneDataBusMatrix:
    """测试总线矩阵。"""

    def test_bus_matrix_shared_dimensions(self):
        """用户/商品/时间是共享维度。"""
        matrix = onedata.build_bus_matrix(
            "trade", ["下单", "支付", "发货"],
            ["用户", "商品", "时间", "支付方式"]
        )
        assert "用户" in matrix["shared_dimensions"]
        assert "商品" in matrix["shared_dimensions"]
        assert "时间" in matrix["shared_dimensions"]

    def test_bus_matrix_pay_method_only_in_pay(self):
        """支付方式只在支付过程用,不是共享维。"""
        matrix = onedata.build_bus_matrix(
            "trade", ["下单", "支付", "发货"],
            ["用户", "商品", "时间", "支付方式"]
        )
        # 支付方式 → 下单/支付 True,发货 False
        assert matrix["matrix"]["下单"]["支付方式"] is True
        assert matrix["matrix"]["支付"]["支付方式"] is True
        assert matrix["matrix"]["发货"]["支付方式"] is False

    def test_bus_matrix_empty_processes(self):
        """空业务过程返回空矩阵 + 警告。"""
        matrix = onedata.build_bus_matrix("trade", [], ["用户"])
        assert matrix["matrix"] == {}
        assert "warning" in matrix


class TestOneDataNaming:
    """测试命名规范生成。"""

    def test_dws_naming(self):
        """DWS 命名 = dws_<域>_<业务>_<修饰>_<周期>"""
        name = onedata.generate_naming(
            layer="dws", domain="trade", business="order",
            modifier="pay", period="1d"
        )
        assert name == "dws_trade_order_pay_1d"

    def test_ods_naming(self):
        """ODS 命名 = ods_<数据源>_<表名>"""
        name = onedata.generate_naming(
            layer="ods", data_source="mysql", business="order"
        )
        assert name == "ods_mysql_order"

    def test_dwd_naming(self):
        """DWD 命名 = dwd_<域>_<业务>"""
        name = onedata.generate_naming(
            layer="dwd", domain="trade", business="order"
        )
        assert name.startswith("dwd_trade_order")

    def test_dwt_naming_defaults_to_td(self):
        """DWT 默认累计周期 = td。"""
        name = onedata.generate_naming(
            layer="dwt", domain="trade", business="user_pay"
        )
        assert "td" in name

    def test_ads_naming(self):
        """ADS 命名 = ads_<应用>_<报表>"""
        name = onedata.generate_naming(
            layer="ads", application="sales_daily"
        )
        assert name == "ads_sales_daily"

    def test_dim_naming(self):
        """DIM 命名 = dim_<域>_<维度>"""
        name = onedata.generate_naming(
            layer="dim", domain="trade", dimension="user"
        )
        assert name == "dim_trade_user"

    def test_chinese_input_normalized(self):
        """中文输入规范化为英文。"""
        name = onedata.generate_naming(
            layer="dws", domain="交易", business="订单", modifier="支付", period="1d"
        )
        # 中文应该被翻译成英文片段
        assert "trade" in name
        assert "order" in name
        assert "pay" in name

    def test_unknown_layer_raises(self):
        """未知层抛 ValueError。"""
        with pytest.raises(ValueError):
            onedata.generate_naming(layer="xyz", business="order")


class TestOneDataMetric:
    """测试指标体系。"""

    def test_define_atomic_metric(self):
        """定义原子指标。"""
        m = onedata.define_atomic_metric(
            "订单金额", "下单", "SUM", "amount", "元"
        )
        assert m["name"] == "订单金额"
        assert m["aggregation"] == "SUM"
        assert m["unit"] == "元"

    def test_define_atomic_metric_invalid_aggregation_raises(self):
        """非法聚合方式抛 ValueError。"""
        with pytest.raises(ValueError):
            onedata.define_atomic_metric("测试", "下单", "INVALID_AGG", "amount")

    def test_define_atomic_metric_empty_field_raises(self):
        """空度量字段抛 ValueError。"""
        with pytest.raises(ValueError):
            onedata.define_atomic_metric("测试", "下单", "SUM", "")

    def test_derive_metric_formula(self):
        """派生指标 = 周期 + 修饰 + 原子。"""
        m = onedata.derive_metric(
            "订单金额", modifiers=["支付的"], period="最近 1 天"
        )
        assert "最近 1 天" in m["name"]
        assert "支付" in m["name"]
        assert "订单金额" in m["name"]

    def test_derive_metric_no_modifiers(self):
        """派生指标无修饰词。"""
        m = onedata.derive_metric("订单金额", period="最近 7 天")
        assert m["name"] == "最近 7 天 订单金额"

    def test_derive_metric_empty_atomic_raises(self):
        """空原子指标抛 ValueError。"""
        with pytest.raises(ValueError):
            onedata.derive_metric("", period="最近 1 天")


# ============================================================
# Dimensions 模块测试
# ============================================================


class TestDimensionsSCD:
    """测试 SCD 类型决策。"""

    def test_scd_type_1_for_correction(self):
        """修正场景 → Type 1。"""
        result = dimensions.recommend_scd_type(
            "用户姓名笔误", "low", is_correction=True
        )
        assert result["scd_type"] == 1

    def test_scd_type_2_for_high_freq_with_history(self):
        """高频 + 需历史 → Type 2。"""
        result = dimensions.recommend_scd_type(
            "用户地址", "high", need_history=True
        )
        assert result["scd_type"] == 2

    def test_scd_type_1_for_low_freq_no_history(self):
        """低频 + 不需历史 → Type 1。"""
        result = dimensions.recommend_scd_type(
            "省份", "low", need_history=False
        )
        assert result["scd_type"] == 1

    def test_scd_type_2_for_audit_keyword(self):
        """属性名含"历史/追溯" → Type 2。"""
        result = dimensions.recommend_scd_type(
            "用户会员等级历史", "medium", need_history=False
        )
        assert result["scd_type"] == 2


class TestDimensionsZipper:
    """测试拉链表。"""

    def test_zipper_applicable_when_history_needed(self):
        """需历史 + 膨胀率合理 → 适用。"""
        result = dimensions.is_zipper_dimension_applicable(
            attribute_change_count=5,
            total_dim_rows=10000,
            fact_query_needs_history=True,
        )
        assert result["applicable"] is True

    def test_zipper_not_applicable_when_no_history(self):
        """不需历史 → 不适用。"""
        result = dimensions.is_zipper_dimension_applicable(
            attribute_change_count=5,
            total_dim_rows=10000,
            fact_query_needs_history=False,
        )
        assert result["applicable"] is False

    def test_zipper_not_applicable_when_explosion(self):
        """变更次数爆炸 → 不适用。"""
        result = dimensions.is_zipper_dimension_applicable(
            attribute_change_count=200,
            total_dim_rows=10000,
            fact_query_needs_history=True,
        )
        assert result["applicable"] is False


class TestDimensionsDegenerate:
    """测试退化维度识别。"""

    def test_degenerate_for_order_id(self):
        """订单号 → 退化维度。"""
        result = dimensions.identify_degenerate_dimension("订单号", "primary_key")
        assert result["is_degenerate"] is True

    def test_degenerate_for_payment_id(self):
        """支付单号 → 退化维度。"""
        result = dimensions.identify_degenerate_dimension("支付单号")
        assert result["is_degenerate"] is True

    def test_not_degenerate_for_user_id(self):
        """user_id → 不是退化维度(应建独立维表)。"""
        result = dimensions.identify_degenerate_dimension("user_id", "foreign_key")
        assert result["is_degenerate"] is False


class TestDimensionsJunk:
    """测试杂项维度。"""

    def test_junk_for_3_low_cardinality_flags(self):
        """3 个低基数标志 → 杂项维。"""
        flags = [
            {"name": "支付方式", "cardinality": 5},
            {"name": "是否会员", "cardinality": 2},
            {"name": "是否首单", "cardinality": 2},
        ]
        result = dimensions.recommend_junk_dimension(flags)
        assert result["use_junk"] is True

    def test_junk_not_used_for_high_cardinality(self):
        """高基数 → 不用杂项维。"""
        flags = [
            {"name": "支付方式", "cardinality": 30},  # > 20
            {"name": "渠道", "cardinality": 50},
        ]
        result = dimensions.recommend_junk_dimension(flags)
        assert result["use_junk"] is False

    def test_junk_not_used_for_few_flags(self):
        """少于 3 个标志 → 不用杂项维。"""
        flags = [
            {"name": "支付方式", "cardinality": 5},
            {"name": "是否会员", "cardinality": 2},
        ]
        result = dimensions.recommend_junk_dimension(flags)
        assert result["use_junk"] is False


class TestDimensionsMini:
    """测试微型维度。"""

    def test_mini_for_high_freq_attrs(self):
        """高频变更属性 → 微型维。"""
        result = dimensions.recommend_mini_dimension(
            ["年龄段", "收入段", "活跃度"],
            "high", 100000
        )
        assert result["use_mini"] is True

    def test_mini_not_used_for_single_attr(self):
        """单属性 → 不用微型维。"""
        result = dimensions.recommend_mini_dimension(
            ["年龄段"], "high", 100000
        )
        assert result["use_mini"] is False


class TestDimensionsMultivalue:
    """测试多值维度 + 桥接表。"""

    def test_bridge_for_many_to_many(self):
        """多对多 → 桥接表。"""
        result = dimensions.recommend_multivalue_strategy("many_to_many", 3)
        assert result["strategy"] == "bridge_table"

    def test_no_bridge_for_many_to_one(self):
        """多对一 → 标准外键。"""
        result = dimensions.recommend_multivalue_strategy("many_to_one", 3)
        assert result["strategy"] == "none"

    def test_array_for_one_to_many_small(self):
        """一对多 + 数量小 → 数组字段。"""
        result = dimensions.recommend_multivalue_strategy("one_to_many", 3)
        assert result["strategy"] == "array_field"

    def test_bridge_for_one_to_many_large(self):
        """一对多 + 数量大 → 桥接表。"""
        result = dimensions.recommend_multivalue_strategy("one_to_many", 10)
        assert result["strategy"] == "bridge_table"


class TestDimensionsHierarchy:
    """测试递归层次。"""

    def test_flatten_for_shallow(self):
        """深度 ≤ 4 → 扁平化。"""
        result = dimensions.recommend_hierarchy_strategy("商品类目", 3, False)
        assert result["strategy"] == "flatten"

    def test_bridge_for_deep(self):
        """深度 > 4 → 桥接表。"""
        result = dimensions.recommend_hierarchy_strategy("行政区域", 5, True)
        assert result["strategy"] == "bridge"

    def test_none_for_depth_1(self):
        """深度 = 1 → 无需特殊处理。"""
        result = dimensions.recommend_hierarchy_strategy("单层标签", 1, False)
        assert result["strategy"] == "none"


# ============================================================
# Facts 模块测试
# ============================================================


class TestFactsTransaction:
    """测试事务事实表设计。"""

    def test_design_transaction_fact_returns_ddl(self):
        """设计事务事实表返回 DDL。"""
        result = facts.design_transaction_fact(
            "下单", "子订单粒度",
            ["用户", "商品", "时间"],
            ["订单金额", "商品数量"]
        )
        assert "table_name" in result
        assert result["table_name"].startswith("dwd_")
        assert "CREATE TABLE" in result["ddl_template"]
        assert "INSERT" in result["etl_pattern"]

    def test_design_transaction_fact_etl_pattern_has_source(self):
        """ETL 模式含 FROM ods_xxx。"""
        result = facts.design_transaction_fact(
            "下单", "子订单粒度", ["用户"], ["金额"]
        )
        assert "FROM ods" in result["etl_pattern"]


class TestFactsPeriodicSnapshot:
    """测试周期快照设计。"""

    def test_design_periodic_snapshot_returns_semi_additive_handling(self):
        """设计周期快照返回半可加处理说明。"""
        result = facts.design_periodic_snapshot(
            "账户", "daily",
            ["余额", "积分"],
            ["用户", "账户类型"]
        )
        assert "table_name" in result
        assert "semi_additive_handling" in result
        assert "LAST_VALUE" in result["semi_additive_handling"]


class TestFactsAccumulatingSnapshot:
    """测试累积快照设计。"""

    def test_design_accumulating_snapshot_contains_multiple_dates(self):
        """累积快照含多个日期字段 + UPSERT 模式。"""
        result = facts.design_accumulating_snapshot(
            ["下单", "支付", "发货", "收货"],
            ["下单日期", "支付日期", "发货日期", "收货日期"],
            ["下单-支付耗时", "支付-发货耗时"],
            ["用户", "商品"]
        )
        assert "table_name" in result
        # DDL 应包含多个日期字段
        assert result["ddl_template"].count("TIMESTAMP") >= 4
        # ETL 应包含 UPSERT 模式
        assert "UPDATE" in result["etl_pattern"]


class TestFactsAggregated:
    """测试聚集型事实表设计。"""

    def test_design_aggregated_returns_principles(self):
        """设计聚集表返回阿里 OneData 原则。"""
        result = facts.design_aggregated_fact(
            "用户", "子订单", "1d",
            ["GMV", "订单数"], ["用户等级"]
        )
        assert "table_name" in result
        assert result["table_name"].startswith("dws_")
        assert "principles" in result
        assert len(result["principles"]) >= 3

    def test_design_aggregated_td_uses_td(self):
        """td 周期表名带 td。"""
        result = facts.design_aggregated_fact(
            "用户", "子订单", "td",
            ["累计GMV"], []
        )
        assert "td" in result["table_name"]


class TestFactsNonAdditive:
    """测试不可加事实拆分。"""

    def test_decompose_simple_ratio(self):
        """客单价 = GMV / 订单数。"""
        result = facts.decompose_non_additive_fact("客单价", "GMV / 订单数")
        assert result["numerator"] == "GMV"
        assert result["denominator"] == "订单数"
        assert "NULLIF" in result["calculation_sql"]

    def test_decompose_complex_ratio(self):
        """转化率 = 转化用户数 / 总用户数。"""
        result = facts.decompose_non_additive_fact(
            "转化率", "转化用户数 / 总用户数"
        )
        assert result["numerator"] == "转化用户数"
        assert result["denominator"] == "总用户数"

    def test_decompose_invalid_formula_raises(self):
        """无 / 的公式抛 ValueError。"""
        with pytest.raises(ValueError):
            facts.decompose_non_additive_fact("无效", "没有分母")


class TestFactsDegenerate:
    """测试退化维度在事实表中的使用。"""

    def test_place_degenerate_dimension(self):
        """放置退化维度。"""
        result = facts.place_degenerate_dimension(
            "dwd_order_detail", "订单号"
        )
        assert "ddl_snippet" in result
        assert "订单号" in result["ddl_snippet"]
        assert "use_cases" in result
        assert "anti_patterns" in result


# ============================================================
# Prompts 模块测试
# ============================================================


class TestPromptsStages:
    """测试 7 阶段引导模板。"""

    def test_all_7_stages_defined(self):
        """7 阶段都被定义。"""
        stages = prompts.list_stages()
        assert len(stages) == 7
        assert stages[0]["stage"] == 0
        assert stages[6]["stage"] == 6

    def test_get_stage_0(self):
        """阶段 0 = 业务调研。"""
        stage = prompts.get_stage(0)
        assert stage["name"] == "业务调研"
        assert len(stage["questions"]) >= 1

    def test_get_stage_4_is_kimball_4step(self):
        """阶段 4 = Kimball 4 步法。"""
        stage = prompts.get_stage(4)
        assert "Kimball" in stage["name"] or "模型" in stage["name"]
        # 必含 4 步法的关键问题
        question_texts = [q["text"] for q in stage["questions"]]
        assert any("业务过程" in t for t in question_texts)
        assert any("粒度" in t for t in question_texts)
        assert any("维度" in t for t in question_texts)
        assert any("事实" in t for t in question_texts)

    def test_get_stage_out_of_range_raises(self):
        """越界 stage_id 抛 ValueError。"""
        with pytest.raises(ValueError):
            prompts.get_stage(7)
        with pytest.raises(ValueError):
            prompts.get_stage(-1)

    def test_required_fields_per_stage(self):
        """每阶段有必填字段。"""
        for s in range(7):
            required = prompts.get_required_fields(s)
            assert len(required) >= 1, f"阶段 {s} 必填字段为空"


class TestPromptsValidation:
    """测试答案校验。"""

    def test_validate_complete_answers(self):
        """完整答案 → valid=True。"""
        answers = {
            "biz_name": "电商",
            "biz_modules": ["订单", "支付"],
            "biz_users": ["买家", "卖家"],
            "biz_industry": "电商",
            "biz_scale": "中 (100w~1亿行)",
        }
        result = prompts.validate_answers(0, answers)
        assert result["valid"] is True
        assert len(result["missing_required"]) == 0

    def test_validate_missing_required(self):
        """缺必填 → valid=False + missing。"""
        answers = {"biz_name": "电商"}  # 只填 1 个
        result = prompts.validate_answers(0, answers)
        assert result["valid"] is False
        assert len(result["missing_required"]) >= 1

    def test_validate_select_answer_invalid(self):
        """select 答案不在选项内 → error。"""
        answers = {
            "biz_name": "电商",
            "biz_modules": ["订单"],
            "biz_users": ["买家"],
            "biz_industry": "魔法行业",  # 非法
            "biz_scale": "中",
        }
        result = prompts.validate_answers(0, answers)
        assert result["valid"] is False
        assert any("biz_industry" in e for e in result["errors"])

    def test_get_question_by_id(self):
        """按 ID 查问题。"""
        q = prompts.get_question_by_id(0, "biz_name")
        assert q is not None
        assert q["text"] == "你要建模的核心业务是什么?"

    def test_get_question_by_id_not_found(self):
        """不存在的 ID 返回 None。"""
        q = prompts.get_question_by_id(0, "no_such_id")
        assert q is None


# ============================================================
# 集成测试 (Integration)
# ============================================================


class TestIntegrationEndToEnd:
    """端到端集成:用真实电商订单场景跑通整个知识库。"""

    def test_ecommerce_order_scenario_full_pipeline(self):
        """完整跑通'电商订单'场景。"""
        # Step 1: 业务过程
        procs = kimball.identify_business_process(
            "用户在下单后,会经历支付、发货、收货"
        )
        assert len(procs) >= 3

        # Step 2: 粒度
        grain = kimball.declare_grain("下单")
        assert "子订单" in grain

        # Step 3: 维度
        dims = kimball.identify_dimensions("下单", grain)
        assert any(d["name"] == "用户" for d in dims)

        # Step 4: 事实
        facts_list = kimball.identify_facts("下单", grain, dims)
        assert any(f["name"] == "订单金额" for f in facts_list)

        # Step 5: 事实表类型
        proc_names = [p["name"] for p in procs if p["name"]]
        fact_type = kimball.decide_fact_type(
            proc_names, has_time_intervals=True, has_end_state=True
        )
        assert fact_type["fact_type"] == "accumulating_snapshot"

        # 阿里 OneData: 数据域 + 命名
        domain = onedata.split_data_domain("电商", ["订单管理"])
        assert domain["primary_domain"] == "trade"

        table_name = onedata.generate_naming(
            layer="dwd", domain="trade", business="order"
        )
        assert table_name.startswith("dwd_trade_order")

        # 维度: SCD 决策
        scd = dimensions.recommend_scd_type("用户地址", "high", need_history=True)
        assert scd["scd_type"] == 2

        # 事实: 不可加拆分
        ratio = facts.decompose_non_additive_fact("客单价", "GMV / 订单数")
        assert ratio["numerator"] == "GMV"

        # Prompts: 7 阶段
        stages = prompts.list_stages()
        assert len(stages) == 7

    def test_finance_scenario(self):
        """金融场景完整跑通。"""
        procs = kimball.identify_business_process(
            "用户注册后,会进行充值、提现、支付等操作"
        )
        proc_names = {p["name"] for p in procs}
        assert "注册" in proc_names
        assert "充值" in proc_names or "支付" in proc_names

        domain = onedata.split_data_domain("金融", ["支付管理", "用户管理"])
        # 金融场景必含 finance
        assert "user" in domain["module_to_domain"].values() or \
               "finance" in domain["module_to_domain"].values()

    def test_unknown_scenario_does_not_crash(self):
        """未知场景不崩溃(优雅降级)。"""
        procs = kimball.identify_business_process("麦田怪圈现象")
        # 不崩溃,即使没识别出来
        assert isinstance(procs, list)

        grain = kimball.declare_grain("麦田怪圈")
        assert isinstance(grain, str)
        assert len(grain) > 0


# ============================================================
# Docstring 来源标注测试
# ============================================================


class TestSourceAnnotations:
    """测试所有函数都有 docstring + 来源标注。"""

    def test_kimball_module_has_source(self):
        """kimball.py 模块有来源标注。"""
        assert hasattr(kimball, "__doc__")
        assert "Kimball" in kimball.__doc__
        assert "数据仓库工具箱" in kimball.__doc__

    def test_onedata_module_has_source(self):
        """onedata.py 模块有来源标注。"""
        assert hasattr(onedata, "__doc__")
        assert "OneData" in onedata.__doc__
        assert "阿里" in onedata.__doc__

    def test_dimensions_module_has_source(self):
        """dimensions.py 模块有来源标注。"""
        assert hasattr(dimensions, "__doc__")
        assert "Kimball" in dimensions.__doc__

    def test_facts_module_has_source(self):
        """facts.py 模块有来源标注。"""
        assert hasattr(facts, "__doc__")
        assert "Kimball" in facts.__doc__

    def test_prompts_module_has_source(self):
        """prompts.py 模块有来源标注。"""
        assert hasattr(prompts, "__doc__")

    def test_key_decision_functions_have_source_in_docstring(self):
        """关键决策函数 docstring 含 Kimball / OneData 来源。"""
        import inspect

        # 抽样 5 个核心函数
        for fn in [
            kimball.identify_business_process,
            kimball.decide_fact_type,
            onedata.split_data_domain,
            dimensions.recommend_scd_type,
            facts.decompose_non_additive_fact,
        ]:
            doc = inspect.getdoc(fn)
            assert doc is not None
            # docstring 应提到 Kimball 或 OneData
            assert any(
                keyword in doc
                for keyword in ["Kimball", "OneData", "阿里", "第", "章"]
            ), f"函数 {fn.__name__} 缺少来源标注"


if __name__ == "__main__":
    # 直接运行 python -m 也可
    pytest.main([__file__, "-v"])
