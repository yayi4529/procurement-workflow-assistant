# Quality Baseline

Measured: 2026-08-17 (Asia/Shanghai)  
Baseline commit: `fb934d8` plus uncommitted Task04 changes  
Python: 3.12.10

## Root unit coverage

Command:

```bash
pytest -q tests/unit --cov=procurement_platform --cov-report=term-missing:skip-covered
```

Result: 264 passed, 30 skipped; total statement coverage 82% (6731 statements, 1225 missed).

Critical Assistant module coverage:

| Module | Coverage |
|---|---:|
| `application/assistant/runtime.py` | 94% |
| `application/assistant/service.py` | 95% |
| `application/assistant/capabilities/intelligence.py` | 87% |
| `adapters/llm/openai_compatible_llm_client.py` | 92% |

CI uses `--cov-fail-under=80`, below the measured 82% baseline to allow platform differences while
preventing a material regression. Backend coverage was not measured in this baseline; backend
quality remains protected by its independent full test job.
