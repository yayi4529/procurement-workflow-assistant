---
name: product-recommendation
description: 按物品名称查询有证据的品牌型号和产品候选。
triggers: [品牌, 型号, 产品推荐, 推荐产品, 推荐一下, 历史推荐]
capabilities: [recommend_products_by_name, recommend_products, compare_products]
priority: 40
phases:
  - name: identify-item
    capabilities: []
    input-parser: applicant-product-name
    on-success: retrieve-candidates
    on-failure: identify-item
    terminal-status: AWAITING_USER
  - name: retrieve-candidates
    capabilities: [recommend_products_by_name, recommend_products, compare_products]
    retry: 1
    on-success: await-selection
    on-failure: COMPLETED
  - name: await-selection
    capabilities: []
    input-parser: applicant-candidate-selection
    on-success: COMPLETED
    on-failure: await-selection
    terminal-status: AWAITING_USER
---

# 产品候选推荐

## 适用条件

需求人按物品名称询问品牌、型号或历史购买候选。

## 执行流程

1. 保留用户给出的准确物品名称；不要先要求电压、功率、安装方式等额外参数。
2. 调用 `ApplicantRecommendationSkillHandler.recommend_by_name`。
3. 按后端返回顺序展示品牌、型号、目录或历史依据。
4. 缺少兼容性证据时明确标注“兼容性待确认”。
5. 只有用户明确选择候选并要求写入草稿时，才转入创建草稿 workflow。

## 后端使用边界

处理器复用 `RecommendProductsByNameCapability`，由它经 BackendClient 查询真实候选。空结果表示当前目录或历史没有候选，不代表市场上不存在该产品。

## 停止条件

取得候选或确认无候选后立即回答，不继续查询无关资产或供应商。
