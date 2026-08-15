from procurement_platform.application.assistant.tooling.purchaser import PreparePurchasePrefillTool


class PreparePurchasePrefillCapability(PreparePurchasePrefillTool):
    description = (
        "Prepare deterministic purchaser-field suggestions from the current request, "
        "authoritative supplier data, and purchase history. It is read-only and never saves."
    )
