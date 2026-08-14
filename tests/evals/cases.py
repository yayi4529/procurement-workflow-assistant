# ruff: noqa: RUF001

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from procurement_platform.domain.enums import RoleCode


@dataclass(frozen=True)
class ExpectedToolCall:
    name: str
    arguments_subset: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments_subset", MappingProxyType(dict(self.arguments_subset)))


@dataclass(frozen=True)
class AgentEvalCase:
    case_id: str
    role: RoleCode
    user_messages: tuple[str, ...]
    expected_tools: tuple[ExpectedToolCall, ...] = ()
    expected_final_state: Mapping[str, object] | None = None
    clarification_expected: bool = False
    expected_no_clarification: bool = False
    fixture: str = "default"
    allowed_roles: tuple[RoleCode, ...] = ()
    initial_role: RoleCode | None = None
    expected_role: RoleCode | None = None

    def __post_init__(self) -> None:
        if not self.case_id or not self.user_messages:
            raise ValueError("eval cases require a stable id and at least one user message")
        if self.clarification_expected and self.expected_no_clarification:
            raise ValueError("clarification expectations are mutually exclusive")
        if self.expected_final_state is not None:
            object.__setattr__(
                self, "expected_final_state", MappingProxyType(dict(self.expected_final_state))
            )


def tool(name: str, **arguments: object) -> ExpectedToolCall:
    return ExpectedToolCall(name=name, arguments_subset=arguments)


APPLICANT_CASES = (
    AgentEvalCase(
        "applicant_create_001",
        RoleCode.APPLICANT,
        ("帮我采购两台精密空调，用于机房制冷扩容。",),
        (tool("update_purchase_draft", quantity=2),),
    ),
    AgentEvalCase(
        "applicant_create_002",
        RoleCode.APPLICANT,
        ("暖通，两台精密空调，用于机房扩容。",),
        (tool("update_purchase_draft", quantity=2),),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "applicant_create_003",
        RoleCode.APPLICANT,
        ("机房扩容需要两台精密空调，专业是暖通。",),
        (tool("update_purchase_draft", quantity=2),),
    ),
    AgentEvalCase(
        "applicant_create_004",
        RoleCode.APPLICANT,
        ("帮机房扩容，采购精密空调两台，暖通。",),
        (tool("update_purchase_draft", quantity=2),),
    ),
    AgentEvalCase(
        "applicant_quantity_001",
        RoleCode.APPLICANT,
        ("数量改成三台。",),
        (tool("update_purchase_draft", quantity=3),),
    ),
    AgentEvalCase(
        "applicant_quantity_002",
        RoleCode.APPLICANT,
        ("改成 3 台。",),
        (tool("update_purchase_draft", quantity=3),),
    ),
    AgentEvalCase(
        "applicant_quantity_003",
        RoleCode.APPLICANT,
        ("刚才数量说错了，改成 3 台。",),
        (tool("update_purchase_draft", quantity=3),),
    ),
    AgentEvalCase(
        "applicant_select_001",
        RoleCode.APPLICANT,
        ("品牌用第一个。",),
        (tool("update_purchase_draft", selection_index=1),),
        fixture="product_recommendations",
    ),
    AgentEvalCase(
        "applicant_select_002",
        RoleCode.APPLICANT,
        ("第一个。",),
        (tool("update_purchase_draft", selection_index=1),),
        fixture="product_recommendations",
    ),
    AgentEvalCase(
        "applicant_select_003",
        RoleCode.APPLICANT,
        ("嗯，就第一个吧。",),
        (tool("update_purchase_draft", selection_index=1),),
        fixture="product_recommendations",
    ),
    AgentEvalCase(
        "applicant_select_004",
        RoleCode.APPLICANT,
        ("还是刚才排第一的那个。",),
        (tool("update_purchase_draft", selection_index=1),),
        fixture="product_recommendations",
    ),
    AgentEvalCase(
        "applicant_model_001",
        RoleCode.APPLICANT,
        ("PEX4。",),
        (tool("update_purchase_draft", model="PEX4"),),
    ),
    AgentEvalCase(
        "applicant_model_002",
        RoleCode.APPLICANT,
        ("型号还是 PEX4。",),
        (tool("update_purchase_draft", model="PEX4"),),
    ),
    AgentEvalCase(
        "applicant_history_001",
        RoleCode.APPLICANT,
        ("品牌跟上次一样。",),
        (tool("query_purchase_requests"),),
        fixture="purchase_history",
    ),
    AgentEvalCase(
        "applicant_new_001", RoleCode.APPLICANT, ("另外再采购两台。",), clarification_expected=True
    ),
    AgentEvalCase(
        "applicant_new_002",
        RoleCode.APPLICANT,
        ("再开一张新的，买两台 UPS。",),
        (tool("update_purchase_draft", quantity=2),),
    ),
    AgentEvalCase(
        "applicant_recommend_001",
        RoleCode.APPLICANT,
        ("先别填品牌，我想看看以前买过什么。",),
        (tool("recommend_product_options"),),
    ),
    AgentEvalCase(
        "applicant_query_001",
        RoleCode.APPLICANT,
        ("帮我查一下我上个月采购过哪些设备。",),
        (tool("query_purchase_requests"),),
    ),
    AgentEvalCase(
        "applicant_multi_001",
        RoleCode.APPLICANT,
        ("把数量改成 2，单位台，理由还是机房扩容。",),
        (tool("update_purchase_draft", quantity=2, unit="台"),),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "applicant_golden_001",
        RoleCode.APPLICANT,
        ("帮我采购两台精密空调，用于机房制冷扩容。", "第一个。", "PEX4。"),
        (
            tool("update_purchase_draft", quantity=2),
            tool("update_purchase_draft", selection_index=1),
            tool("update_purchase_draft", model="PEX4"),
        ),
        fixture="applicant_golden",
    ),
)

BUILDING_MANAGER_CASES = (
    AgentEvalCase(
        "building_recommend_001",
        RoleCode.BUILDING_MANAGER,
        ("给我推荐几个靠谱供应商。",),
        (tool("recommend_suppliers_for_requirement"),),
    ),
    AgentEvalCase(
        "building_recommend_002",
        RoleCode.BUILDING_MANAGER,
        ("找之前合作最多的。",),
        (tool("recommend_suppliers_for_requirement"),),
    ),
    AgentEvalCase(
        "building_recommend_003",
        RoleCode.BUILDING_MANAGER,
        ("哪个供应商以前合作次数最多？",),
        (tool("recommend_suppliers_for_requirement"),),
    ),
    AgentEvalCase(
        "building_select_001",
        RoleCode.BUILDING_MANAGER,
        ("就第一个吧。",),
        (tool("update_review_draft", selection_index=1),),
        fixture="supplier_recommendations",
    ),
    AgentEvalCase(
        "building_select_002",
        RoleCode.BUILDING_MANAGER,
        ("第一家吧。",),
        (tool("update_review_draft", selection_index=1),),
        fixture="supplier_recommendations",
    ),
    AgentEvalCase(
        "building_select_003",
        RoleCode.BUILDING_MANAGER,
        ("选第一项。",),
        (tool("update_review_draft", selection_index=1),),
        fixture="supplier_recommendations",
    ),
    AgentEvalCase(
        "building_select_004",
        RoleCode.BUILDING_MANAGER,
        ("还是之前合作最多的那个。",),
        (tool("update_review_draft", selection_index=1),),
        fixture="supplier_recommendations",
    ),
    AgentEvalCase(
        "building_contact_001",
        RoleCode.BUILDING_MANAGER,
        ("联系人用张工，电话 13800138000。",),
        (tool("update_review_draft", contact_person="张工", contact_phone="13800138000"),),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "building_date_001",
        RoleCode.BUILDING_MANAGER,
        ("预计 8 月 20 日到。",),
        (tool("update_review_draft"),),
    ),
    AgentEvalCase(
        "building_date_002",
        RoleCode.BUILDING_MANAGER,
        ("预计下周三到。",),
        (tool("update_review_draft"),),
    ),
    AgentEvalCase(
        "building_price_001",
        RoleCode.BUILDING_MANAGER,
        ("报价每台 12800，需要合同。",),
        (tool("update_review_draft", proposed_unit_price=12800, contract_required=True),),
    ),
    AgentEvalCase(
        "building_multi_001",
        RoleCode.BUILDING_MANAGER,
        ("联系人张工，电话 13800138000，报价 12800，需要合同。",),
        (
            tool(
                "update_review_draft",
                contact_person="张工",
                contact_phone="13800138000",
                proposed_unit_price=12800,
                contract_required=True,
            ),
        ),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "building_profile_001",
        RoleCode.BUILDING_MANAGER,
        ("先别选供应商，我想看看 A 供应商以前的报价。",),
        (tool("query_supplier_profile"),),
    ),
    AgentEvalCase(
        "building_profile_002",
        RoleCode.BUILDING_MANAGER,
        ("这个供应商联系方式是多少？",),
        (tool("query_supplier_profile"),),
        fixture="selected_supplier",
    ),
    AgentEvalCase(
        "building_profile_003",
        RoleCode.BUILDING_MANAGER,
        ("第一个供应商以前买过几次？",),
        (tool("query_supplier_profile", selection_index=1),),
        fixture="supplier_recommendations",
    ),
    AgentEvalCase(
        "building_negation_001",
        RoleCode.BUILDING_MANAGER,
        ("不要 A，选第二个。",),
        (tool("update_review_draft", selection_index=2),),
        fixture="supplier_recommendations",
    ),
    AgentEvalCase(
        "building_contract_001",
        RoleCode.BUILDING_MANAGER,
        ("合同不用。",),
        (tool("update_review_draft", contract_required=False),),
    ),
    AgentEvalCase(
        "building_date_003",
        RoleCode.BUILDING_MANAGER,
        ("不是 8 月 20，是 8 月 22。",),
        (tool("update_review_draft"),),
    ),
    AgentEvalCase(
        "building_multi_002",
        RoleCode.BUILDING_MANAGER,
        ("联系人还是张工，电话 13800138000，预计 20 号到。",),
        (tool("update_review_draft", contact_person="张工", contact_phone="13800138000"),),
    ),
    AgentEvalCase(
        "building_golden_001",
        RoleCode.BUILDING_MANAGER,
        (
            "帮我找之前合作最多的供应商。",
            "就第一个吧。",
            "联系人张工，电话 13800138000，报价 12800，需要合同。",
        ),
        (
            tool("recommend_suppliers_for_requirement"),
            tool("update_review_draft", selection_index=1),
            tool("update_review_draft", contact_person="张工"),
        ),
        fixture="building_golden",
    ),
)

PURCHASER_CASES = (
    AgentEvalCase(
        "purchaser_open_001",
        RoleCode.PURCHASER,
        ("帮我打开 PR202608001。",),
        (tool("query_purchase_requests"),),
    ),
    AgentEvalCase(
        "purchaser_open_002",
        RoleCode.PURCHASER,
        ("看看这个采购单。",),
        (tool("query_purchase_requests"),),
        fixture="active_requirement",
    ),
    AgentEvalCase(
        "purchaser_prefill_001",
        RoleCode.PURCHASER,
        ("把能根据供应商资料自动补的都补一下。",),
        (tool("prepare_purchase_prefill"), tool("fill_selected_supplier_profile")),
        fixture="purchase_prefill",
    ),
    AgentEvalCase(
        "purchaser_prefill_002",
        RoleCode.PURCHASER,
        ("把能自动补的都补一下，然后告诉我还缺什么。",),
        (tool("prepare_purchase_prefill"),),
        fixture="purchase_prefill",
    ),
    AgentEvalCase(
        "purchaser_profile_001",
        RoleCode.PURCHASER,
        ("这个供应商税号是多少？",),
        (tool("query_supplier_profile"),),
        fixture="selected_supplier",
    ),
    AgentEvalCase(
        "purchaser_profile_002",
        RoleCode.PURCHASER,
        ("银行账号是什么？",),
        (tool("query_supplier_profile"),),
        fixture="selected_supplier",
    ),
    AgentEvalCase(
        "purchaser_price_001",
        RoleCode.PURCHASER,
        ("实际成交价每台 12680。",),
        (tool("update_purchase_execution_draft", actual_unit_price=12680),),
    ),
    AgentEvalCase(
        "purchaser_price_002",
        RoleCode.PURCHASER,
        ("成交价改成 12500。",),
        (tool("update_purchase_execution_draft", actual_unit_price=12500),),
    ),
    AgentEvalCase(
        "purchaser_price_003",
        RoleCode.PURCHASER,
        ("还是按以前那个价格。",),
        clarification_expected=True,
        fixture="ambiguous_prices",
    ),
    AgentEvalCase(
        "purchaser_history_001",
        RoleCode.PURCHASER,
        ("以前买过哪些价格？",),
        (tool("prepare_purchase_prefill"),),
        fixture="purchase_history",
    ),
    AgentEvalCase(
        "purchaser_prefill_003",
        RoleCode.PURCHASER,
        ("供应商资料补一下，价格我自己确认。",),
        (tool("fill_selected_supplier_profile"),),
        fixture="purchase_prefill",
    ),
    AgentEvalCase(
        "purchaser_prefill_004",
        RoleCode.PURCHASER,
        ("能确定的先填，推荐值不要直接用。",),
        (tool("prepare_purchase_prefill"),),
        fixture="purchase_prefill",
    ),
    AgentEvalCase(
        "purchaser_prefill_005",
        RoleCode.PURCHASER,
        ("把税号和银行资料补上，实际单价等我确认。",),
        (tool("fill_selected_supplier_profile"),),
        fixture="purchase_prefill",
    ),
    AgentEvalCase(
        "purchaser_price_004", RoleCode.PURCHASER, ("价格先别填。",), expected_no_clarification=True
    ),
    AgentEvalCase(
        "purchaser_profile_003",
        RoleCode.PURCHASER,
        ("看看供应商资料，但别改采购草稿。",),
        (tool("query_supplier_profile"),),
        fixture="selected_supplier",
    ),
    AgentEvalCase(
        "purchaser_prefill_006",
        RoleCode.PURCHASER,
        ("资料里能确认的填上，不确定的列出来。",),
        (tool("prepare_purchase_prefill"),),
        fixture="purchase_prefill",
    ),
    AgentEvalCase(
        "purchaser_price_005",
        RoleCode.PURCHASER,
        ("单价一万二千六百八。",),
        (tool("update_purchase_execution_draft", actual_unit_price=12680),),
    ),
    AgentEvalCase(
        "purchaser_query_001",
        RoleCode.PURCHASER,
        ("这张单现在是什么状态？",),
        (tool("query_purchase_requests"),),
        fixture="active_requirement",
    ),
    AgentEvalCase(
        "purchaser_safety_001",
        RoleCode.PURCHASER,
        ("直接提交仓库吧。",),
        clarification_expected=True,
    ),
    AgentEvalCase(
        "purchaser_golden_001",
        RoleCode.PURCHASER,
        ("把能自动补的都补一下，再告诉我还有什么需要确认。", "实际成交价 12680。"),
        (
            tool("prepare_purchase_prefill"),
            tool("fill_selected_supplier_profile"),
            tool("update_purchase_execution_draft", actual_unit_price=12680),
        ),
        fixture="purchaser_golden",
    ),
)

WAREHOUSE_CASES = (
    AgentEvalCase(
        "warehouse_multi_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("到了 10 台，放 A-03。",),
        (tool("update_warehouse_receipt_draft", received_quantity=10, warehouse_location="A-03"),),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "warehouse_partial_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("实际到了八台，少两台，厂家漏发。",),
        (tool("update_warehouse_receipt_draft", received_quantity=8),),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "warehouse_partial_002",
        RoleCode.WAREHOUSE_MANAGER,
        ("到了 8 台，库位 A-03，备注厂家漏发。",),
        (tool("update_warehouse_receipt_draft", received_quantity=8, warehouse_location="A-03"),),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "warehouse_complete_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("全部到齐了，放 B-12。",),
        (tool("update_warehouse_receipt_draft", warehouse_location="B-12"),),
        fixture="ordered_10",
    ),
    AgentEvalCase(
        "warehouse_quantity_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("收到 10 台。",),
        (tool("update_warehouse_receipt_draft", received_quantity=10),),
    ),
    AgentEvalCase(
        "warehouse_location_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("库位改成 C-02。",),
        (tool("update_warehouse_receipt_draft", warehouse_location="C-02"),),
    ),
    AgentEvalCase(
        "warehouse_partial_003",
        RoleCode.WAREHOUSE_MANAGER,
        ("少了 2 台。",),
        clarification_expected=True,
        fixture="ordered_10",
    ),
    AgentEvalCase(
        "warehouse_partial_004",
        RoleCode.WAREHOUSE_MANAGER,
        ("厂家少发两台，实际收 8 台。",),
        (tool("update_warehouse_receipt_draft", received_quantity=8),),
        expected_no_clarification=True,
    ),
    AgentEvalCase(
        "warehouse_partial_005",
        RoleCode.WAREHOUSE_MANAGER,
        ("少两台，厂家没发够。",),
        (tool("update_warehouse_receipt_draft"),),
        fixture="ordered_10",
    ),
    AgentEvalCase(
        "warehouse_partial_006",
        RoleCode.WAREHOUSE_MANAGER,
        ("到了八台。",),
        (tool("update_warehouse_receipt_draft", received_quantity=8),),
        clarification_expected=True,
        fixture="ordered_10",
    ),
    AgentEvalCase(
        "warehouse_multi_002",
        RoleCode.WAREHOUSE_MANAGER,
        ("A-03 收了八台，厂家漏发两台。",),
        (tool("update_warehouse_receipt_draft", received_quantity=8, warehouse_location="A-03"),),
    ),
    AgentEvalCase(
        "warehouse_modify_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("不是 A-03，改放 C-02。",),
        (tool("update_warehouse_receipt_draft", warehouse_location="C-02"),),
    ),
    AgentEvalCase(
        "warehouse_query_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("看看这张待入库单。",),
        (tool("query_purchase_requests"),),
        fixture="active_requirement",
    ),
    AgentEvalCase(
        "warehouse_safety_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("直接确认完成。",),
        clarification_expected=True,
    ),
    AgentEvalCase(
        "warehouse_golden_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("到了八台，放 A-03，少两台是厂家漏发。",),
        (tool("update_warehouse_receipt_draft", received_quantity=8, warehouse_location="A-03"),),
        expected_no_clarification=True,
        fixture="warehouse_golden",
    ),
)

MULTI_ROLE_CASES = (
    AgentEvalCase(
        "multi_role_applicant_to_manager_001",
        RoleCode.BUILDING_MANAGER,
        ("看一下现在有哪些待审核的采购单。",),
        (tool("query_purchase_requests"),),
        fixture="multi_role_review_queue",
        allowed_roles=(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        initial_role=RoleCode.APPLICANT,
        expected_role=RoleCode.BUILDING_MANAGER,
    ),
    AgentEvalCase(
        "multi_role_manager_to_applicant_001",
        RoleCode.APPLICANT,
        ("我还想新采购两台 UPS。",),
        (tool("update_purchase_draft", quantity=2),),
        fixture="multi_role_new_request",
        allowed_roles=(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        initial_role=RoleCode.BUILDING_MANAGER,
        expected_role=RoleCode.APPLICANT,
    ),
    AgentEvalCase(
        "multi_role_keep_current_001",
        RoleCode.BUILDING_MANAGER,
        ("这个供应商怎么样？",),
        (tool("query_supplier_profile"),),
        fixture="multi_role_selected_supplier",
        allowed_roles=(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        initial_role=RoleCode.BUILDING_MANAGER,
        expected_role=RoleCode.BUILDING_MANAGER,
    ),
    AgentEvalCase(
        "multi_role_ambiguous_001",
        RoleCode.APPLICANT,
        ("看看这单。",),
        fixture="multi_role_ambiguous",
        allowed_roles=(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        initial_role=RoleCode.APPLICANT,
        expected_role=RoleCode.APPLICANT,
    ),
)

ALL_CASES = (
    APPLICANT_CASES + BUILDING_MANAGER_CASES + PURCHASER_CASES + WAREHOUSE_CASES + MULTI_ROLE_CASES
)
