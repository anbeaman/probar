# 贡献指南

欢迎为 probar 贡献代码。**实质性变更前请先读[工程规范 / 总工程师宪章](docs/ENGINEERING_GUIDE.md)**——
它是本项目的硬性规则;本文件只讲"怎么上手、怎么过门禁"。

## 开发环境

```bash
git clone https://github.com/anbeaman/probar
cd probar
python -m pip install -e ".[dev]"   # httpx/pandas + ruff/mypy/pytest
```

## 提交前必过(本地 = CI 门禁)

```bash
ruff check probar tests scripts     # lint + import 排序
mypy probar                         # 类型
pytest                              # 离线测试(禁止联网)
```

三者全绿才提 PR。**单元测试不得联网**——实网验证交给 canary。

## 加一个新接口(标准流程)

严格按[宪章 §3 onboarding 清单](docs/ENGINEERING_GUIDE.md#3-新数据源--新接口-onboarding-清单):

1. live 探针抓真实响应 → 冻结成 `tests/fixtures/<source>_<iface>.json`
2. 写纯函数 parser(`probar/providers/<source>/parsers.py`)
3. 写 client 方法(参数规范化 + referer + **限流** + 归一化 + provenance)
4. 更新能力矩阵 `probar/core/capabilities.py`
5. 加离线测试:字段/类型/边界 + 错误样本(空→`NoData`、缺字段→`SchemaChanged`)
6. 补文档(接口表、字段含单位、限制、质量档)
7. 核心接口加 canary 探针
8. 写 `CHANGELOG.md` 条目;PR 描述写明:数据源、接口、字段、限流策略、已知风险

## 分支 / 提交 / PR

- 从 `main` 切分支:`feat/<source>-<iface>`、`fix/<...>`、`docs/<...>`。
- 提交信息:`<type>: <简述>`(type ∈ feat/fix/docs/test/refactor/chore);破坏性变更标 `!` 并在正文说明。
- PR 走 `.github/PULL_REQUEST_TEMPLATE.md`,勾选:测试 / 文档 / 兼容性 / canary 影响。
- `main` 受保护:CI 必过 + 复核通过才能合并。

## 复核工作流(本项目特有)

probar 维护实行**交叉复核**:实质性变更在合入前由维护者独立复核,分歧显式标注裁决。
外部贡献者正常提 PR 即可,维护者会在合并前走这套复核。

## 报告问题

用 `.github/ISSUE_TEMPLATE/` 对应模板,**务必附**:probar 版本、接口、symbol、参数、完整错误栈、是否稳定复现。
分诊标签与 SLA 见[宪章 §10](docs/ENGINEERING_GUIDE.md#10-issue-分诊与回复)。

## 许可

贡献即同意以 [MIT](LICENSE) 授权;封装的是非官方接口,请遵守各数据平台 ToS(见 README 免责声明)。
