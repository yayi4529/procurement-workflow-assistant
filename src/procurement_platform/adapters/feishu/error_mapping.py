from procurement_platform.domain.errors import FeishuDeliveryError, FeishuError, FeishuTimeoutError


def map_feishu_delivery_error(error: Exception) -> FeishuError:
    """Map SDK/runtime failures without exposing SDK response objects upstream."""
    if isinstance(error, TimeoutError):
        return FeishuTimeoutError("Feishu delivery timed out")
    if isinstance(error, FeishuDeliveryError):
        return error
    return FeishuDeliveryError("Feishu delivery failed")
