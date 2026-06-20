<!-- 变更前请读 docs/ENGINEERING_GUIDE.md(工程规范)。 -->

## 变更说明
<!-- 这个 PR 做了什么、为什么 -->

## 类型
- [ ] feat(新接口/新源) · [ ] fix · [ ] docs · [ ] test · [ ] refactor · [ ] chore
- [ ] 破坏性变更(改返回列/异常/默认值/语义)→ 已在正文说明并评估 SemVer 影响

## 涉及数据源 / 接口
<!-- 如 pb.dc.fund_flow;新接口请补:数据源、字段(含单位)、限流策略、已知风险 -->

## 自检清单(对应工程规范门禁)
- [ ] `ruff check` / `mypy probar` / `pytest` 本地全绿
- [ ] 新接口/改动**带离线测试**(parser 字段/类型/边界 + 错误样本)
- [ ] **单测不联网**(实网验证交给 canary)
- [ ] 更新了能力矩阵 `probar/core/capabilities.py`(若新增/调整接口)
- [ ] 更新了文档(接口表、字段含单位、限制、质量档)
- [ ] 加了 `CHANGELOG.md` 条目(非 docs-only)
- [ ] 评估了对 canary 的影响(是否需新增/调整探针)
- [ ] 不含 token/cookie/密钥
