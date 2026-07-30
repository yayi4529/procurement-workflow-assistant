from procurement_platform.domain.enums import RequirementStatus

_REQUIREMENT_STATUS_LABELS = {
    RequirementStatus.DRAFT: "草稿",
    RequirementStatus.PENDING_REVIEW: "待楼长审核",
    RequirementStatus.REJECTED: "已驳回",
    RequirementStatus.PENDING_PURCHASE: "待采购",
    RequirementStatus.PURCHASING: "采购中",
    RequirementStatus.PENDING_WAREHOUSE: "待入库",
    RequirementStatus.COMPLETED: "已完成",
}


def requirement_status_label(status: RequirementStatus) -> str:
    return _REQUIREMENT_STATUS_LABELS[status]
