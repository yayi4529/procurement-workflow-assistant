from procurement_platform.application.status_labels import requirement_status_label
from procurement_platform.domain.enums import RequirementStatus


def test_all_requirement_statuses_have_chinese_labels() -> None:
    labels = {status: requirement_status_label(status) for status in RequirementStatus}
    assert labels == {
        RequirementStatus.DRAFT: "草稿",
        RequirementStatus.PENDING_REVIEW: "待楼长审核",
        RequirementStatus.REJECTED: "已驳回",
        RequirementStatus.PENDING_PURCHASE: "待采购",
        RequirementStatus.PURCHASING: "采购中",
        RequirementStatus.PENDING_WAREHOUSE: "待入库",
        RequirementStatus.COMPLETED: "已完成",
    }
