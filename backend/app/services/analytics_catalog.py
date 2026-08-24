from app.schemas.analytics import (
    AnalyticsCatalogData,
    AnalyticsField,
    AnalyticsMetric,
    AnalyticsView,
)


def analytics_catalog(*, synthetic_default_included: bool) -> AnalyticsCatalogData:
    request_fields = [
        AnalyticsField(name="request_no", description="采购单号", data_type="string"),
        AnalyticsField(name="request_status", description="采购单状态", data_type="string"),
        AnalyticsField(name="request_type", description="需求类型", data_type="string"),
        AnalyticsField(name="building_id", description="楼宇ID", data_type="integer"),
        AnalyticsField(name="building_name", description="楼宇名称", data_type="string"),
        AnalyticsField(name="device_profession", description="设备专业", data_type="string"),
        AnalyticsField(name="device_name", description="单据设备名称", data_type="string"),
        AnalyticsField(name="created_at", description="创建时间", data_type="datetime"),
        AnalyticsField(name="submitted_at", description="提交时间", data_type="datetime"),
        AnalyticsField(name="completed_at", description="完成时间", data_type="datetime"),
    ]
    item_fields = request_fields + [
        AnalyticsField(name="request_item_id", description="采购项ID", data_type="integer"),
        AnalyticsField(name="item_name", description="采购物品名称", data_type="string"),
        AnalyticsField(name="item_kind", description="采购项类型", data_type="string"),
        AnalyticsField(name="brand", description="实际或申请品牌", data_type="string"),
        AnalyticsField(name="model", description="实际或申请型号", data_type="string"),
        AnalyticsField(name="requested_quantity", description="申请数量", data_type="decimal"),
        AnalyticsField(name="purchased_quantity", description="实际采购数量", data_type="decimal"),
        AnalyticsField(name="unit", description="计量单位", data_type="string"),
        AnalyticsField(name="supplier_id", description="供应商ID", data_type="integer"),
        AnalyticsField(name="supplier_name", description="供应商名称", data_type="string"),
        AnalyticsField(name="actual_unit_price", description="实际单价", data_type="decimal"),
        AnalyticsField(name="actual_total_price", description="实际总价", data_type="decimal"),
        AnalyticsField(name="purchased_at", description="采购时间", data_type="datetime"),
        AnalyticsField(name="received_quantity", description="累计收货数量", data_type="decimal"),
        AnalyticsField(name="last_received_at", description="最后收货时间", data_type="datetime"),
        AnalyticsField(name="delivery_days", description="采购至最后收货天数", data_type="integer"),
    ]
    return AnalyticsCatalogData(
        version="1.0",
        dialect="mysql",
        synthetic_default_included=synthetic_default_included,
        views=[
            AnalyticsView(
                name="analytics_purchase_request_fact",
                description="脱敏采购单事实，一行一张采购单",
                grain="request_no",
                fields=request_fields,
            ),
            AnalyticsView(
                name="analytics_purchase_item_fact",
                description="脱敏采购项事实，一行一个有效采购项",
                grain="request_item_id",
                fields=item_fields,
            ),
        ],
        metrics=[
            AnalyticsMetric(
                name="采购单数",
                description="去重采购单数量",
                expression="COUNT(DISTINCT request_no)",
            ),
            AnalyticsMetric(name="采购项次数", description="采购项记录数量", expression="COUNT(*)"),
            AnalyticsMetric(
                name="申请数量", description="申请数量合计", expression="SUM(requested_quantity)"
            ),
            AnalyticsMetric(
                name="采购金额",
                description="实际采购总价合计",
                expression="SUM(actual_total_price)",
            ),
            AnalyticsMetric(
                name="平均交付周期",
                description="仅统计已收货项的平均交付天数",
                expression="AVG(delivery_days)",
            ),
        ],
    )
