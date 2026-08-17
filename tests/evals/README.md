# Agent Natural Language Eval

这里测量 Agent 的可观察行为：Tool 选择、关键参数、最终业务状态、角色选择、错误写入、无效追问和正式动作越界；不比较固定回复全文，也不读取或保存模型私有推理。多角色 Case 额外统计 Role Selection Accuracy、Unnecessary Role Switch 和 Unauthorized Role Selection，最后一项必须保持为零。

普通 `pytest` 运行 deterministic harness 和 case catalog 检查，快速、无网络、无 API 成本。真实模型测试必须同时设置 `RUN_LLM_EVALS=1`、`PROCUREMENT_LLM_API_KEY` 和 `PROCUREMENT_LLM_MODEL`，并复用项目的 OpenAI-compatible client、当前模型和超时配置；缺少配置时只会 skip，绝不回退到 Fake LLM。

```powershell
pytest -q tests/evals
$env:RUN_LLM_EVALS='1'
pytest -q tests/evals/test_real_llm_language_eval.py
```

`cases.py` 中 Case 只保存用户表达和可观察期望，fixture 名称描述所需的真实业务快照。新增 Case 时保持 ID 稳定，参数使用 subset 匹配，并为不可唯一确定的输入标记 `clarification_expected`。真实 baseline 只有在对应 Backend、Session、Requirement、Recommendations 和 History fixture 明确准备后才执行；不得用虚构状态代替。

禁止为了让 Eval 通过向业务 Python 增加自然语言 alias、关键词、Regex、`before_run` 或写死 Tool 顺序。失败应先定位 Context、Prompt、Tool schema、模型或 Backend fixture 层。
