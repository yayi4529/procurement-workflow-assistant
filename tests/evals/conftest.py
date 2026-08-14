import os

import pytest


def real_llm_eval_enabled() -> bool:
    return os.getenv("RUN_LLM_EVALS") == "1"


@pytest.fixture
def require_real_llm() -> None:
    if not real_llm_eval_enabled():
        pytest.skip("real LLM eval requires RUN_LLM_EVALS=1")
    missing = [
        name for name in ("PROCUREMENT_LLM_API_KEY", "PROCUREMENT_LLM_MODEL") if not os.getenv(name)
    ]
    if missing:
        pytest.skip(f"real LLM eval configuration missing: {', '.join(missing)}")
