# probar 工程规范 / 总工程师宪章

> 本文件是 probar 的项目宪法,约束**所有**实质性变更。目标:把 probar 做成**可长期维护的精品数据层**——
> 比同类更稳、更可观测、坏了能最快发现最快修。
>
> **核心原则:文档解释规则,CI 执行规则。** 能固化成 CI / pre-commit / 模板 / lint 的规范,一律固化;
> 本文档只负责解释"为什么"和"怎么做",**不靠自觉**。每条带 🔒 的规则都有(或计划有)自动门禁,
> 见文末「执行状态清单」。

维护协作流程:本项目实行**交叉复核**——任何实质性变更在合入前必须经独立复核,分歧显式标给维护者裁决。

---

## 0. 角色与原则

- **定位**:数据层优先。probar 只负责把数据源统一、可靠地喂出;回测/策略交给 backtrader/vnpy 等。
- **不靠接口数量赢,靠可靠性赢**:宁可少做一个接口,也要把已有接口做到稳定、可监控、可复现。
- **诚实**:命名空间只暴露该源真实支持的接口;不静默降级、不静默吞错、不返回脏数据。
- **小步快跑**:每次变更尽量小、可复核、可回滚;补丁优先于大重构。

---

## 1. 接口规范 🔒

- **命名**:`pb.<source>.<resource>()`,如 `pb.dc.kline()`。`pb.auto` 只做路由,**不引入新语义**。
- **只暴露真实支持的接口**:某源没有的能力,命名空间里**不存在该方法**(访问得到 `AttributeError`),
  而不是运行时抛"不支持"。能力矩阵见 `pb.capabilities()`(三源能力**参考**,非方法清单)。
- **参数约定**:常用参数统一命名,**但非适用参数不得伪造**:
  - 证券代码 `symbol`;日期区间 `start` / `end`,格式 `YYYY-MM-DD`;频率 `freq`;复权 `adjust`∈`{None,"qfq","hfq"}`。
  - 某接口天然没有的参数(如龙虎榜按 `date`)就不要硬塞 `symbol/start/end`。
- **返回**:默认 `pandas.DataFrame`;列名 `snake_case`;时间列统一 `date`/`time`(`datetime64`);
  **金额、成交量单位必须在文档与 docstring 写明**。单只快照可返回 `dict`。
- **跨源同名接口**返回**统一核心列**;源特有但**稳定**的字段 → 作为额外**列**(文档登记含义与单位),不塞进 `df.attrs`;
  冗余/不稳定的原始响应**默认不返回**,仅 `include_raw=True` 时附 `df.attrs["raw"]`,且**不得含 cookie/token/敏感 header**。
- **provenance**:轻量溯源信息写入 `df.attrs["provenance"]`,只含 `source/interface/fetched_at/adjust/quality_flags`。
  ⚠️ `df.attrs` **不是稳定公共 API**(pandas 运算/保存易丢);`raw`/`provenance` 仅作调试/溯源元数据、**不作向后兼容承诺**,不得承载业务必需字段。
- **无数据**:源信号无数据(空容器 / 空区间 / 非交易日)→ 抛 `NoData`;其余异常走错误模型(下)。
  > 是否改为"合法空结果返回空 DataFrame"属**公共行为变更**,需走 ADR + minor,不得随意改。
- **错误模型**(`probar.core.errors`,均继承 `ProbarError`):
  | 异常 | 含义 |
  |---|---|
  | `InvalidSymbol` | 代码非法/无法解析 |
  | `NotSupported` | 该源不支持此能力(命名空间无此方法即 `AttributeError`;本异常用于 auto 路由选定源不支持、或参数组合/运行期能力探测不支持) |
  | `NetworkError` | 网络/超时/源不可用(穷尽重试后) |
  | `RateLimited` | 被限频 |
  | `NoData` | 源信号无数据(空区间/非交易日/无此记录) |
  | `ParseError` | 响应能拿到但解析失败 |
  | `SchemaChanged` | 响应结构/字段与契约不符(上游接口变更)——canary 头号目标 |

  > v0.1 现状:已具备 `NotSupported/NetworkError/RateLimited/NoData/SchemaChanged`;
  > `InvalidSymbol`、`ParseError` 为本规范新增项,按 minor 向后兼容补齐。

---

## 2. 数据质量分级 🔒

每个接口在能力矩阵/文档中标注质量档:

- `stable` —— 有 canary、有契约测试、可生产使用(如 `pb.dc.kline`)。
- `degraded` —— 上游近期不稳/已知缺陷,可用但不保证。
- `experimental` —— best-effort,随时可能失效(如同花顺反爬接口);需 `pip install "probar[ths]"`。
- `unsupported` —— 该源无此能力(矩阵里为 ❌)。

降级/恢复必须改矩阵 + CHANGELOG,**不得静默**。

---

## 3. 新数据源 / 新接口 onboarding 清单 🔒

新增任何接口走**固定流程**(顺序不可省):

1. **live 探针**先抓真实响应,**冻结为 fixture**(`tests/fixtures/<source>_<iface>.json`,裁剪到 2–3 行)。
2. 写**纯函数 parser**(输入 dict→输出 DataFrame/dict,不碰网络)。
3. 写 **client 方法**(参数规范化、referer、限流、归一化、provenance)。
4. 更新 **能力矩阵** `probar/core/capabilities.py`。
5. 加**离线测试**:parser 字段/类型/边界 + 错误样本(空数据→`NoData`、缺字段→`SchemaChanged`)。
6. 补**文档**:接口表、字段表(含单位)、限制与质量档。
7. 核心接口加入 **canary 探针**。
8. PR 描述写明:数据源、接口、字段、限流策略、已知风险。

> 新数据源额外要求:建 `probar/providers/<source>/` 子包,**不得污染 `probar/core`**;独立配置与传输(如 TDX 走 TCP 不复用 HTTP 层)。

---

## 4. 接口更新与废弃 🔒

- 遵循 **SemVer**:
  - **patch**:修 parser/bug,**不改公共契约**。
  - **minor**:新增接口/源/兼容字段。
  - **major**:删接口、改默认语义、改返回列含义。
- **废弃政策**:先发 `DeprecationWarning` + 文档标注 `Deprecated since vX.Y`,**至少保留一个 minor 周期**再移除。
  弃用接口必须有断言 `DeprecationWarning` 的测试。
- **向后兼容承诺**:返回列名、异常类型、参数默认值的变更视为破坏性,需走 major + ADR。

---

## 5. 测试规范 🔒

五层,职责分明:

| 层 | 是否联网 | 作用 | 是否 PR 门禁 |
|---|---|---|---|
| Unit | 否 | 纯函数(symbols/限流/缓存等) | 是 |
| Parser fixture | 否 | 冻结真实响应,验字段/类型/边界 | 是 |
| Contract | 否 | 公共 API 返回列、异常、空数据行为 | 是 |
| Integration | 受控 | 端到端,手工/受控环境 | 否 |
| Canary | 是 | 定时实网,少量代表 symbol | 否(独立 workflow) |

- 🔒 **单测禁止联网**:默认禁网,仅 `@pytest.mark.network` 用例可联网且不进普通 CI 门禁。
- 新接口**必须**带 parser 测试 + 至少一个错误样本测试。
- 修 bug **必须**先加复现该 bug 的回归测试。

---

## 6. canary 与接口修复闭环 🔒

- canary 失败**必须分类**:`network` / `ratelimit` / `nodata` / `schema_changed` / `parse_error` / `provider_down`。
  输出**结构化 JSON**,含 endpoint/symbol/时间/**脱敏**响应摘要。
- `schema_changed` / `parse_error` → **自动开/更新 issue**(标签 `type:schema-change`),附定位信息。
- **修复流程**:用捕获的真实响应复现 → 更新 fixture → 改 parser/endpoint → 加回归测试 → 发 **patch** 版。
- 连续失败但确认是上游问题(非代码)→ 标 `degraded`,**不要急着改 API**。
- canary 分级:核心接口每交易日;低频/重接口 weekly。GitHub runner 在境外会误报 →
  v0.2 起主巡检放国内节点,GitHub Actions 仅 smoke。

---

## 7. 代码规范 🔒

- `ruff`(lint+isort)+ `mypy` 强制过;行宽 100;`py310+`。
- 全量类型标注;公共函数/类写 docstring(说明单位、返回、异常)。
- 严守模块边界:`core/`(共享基建)← `providers/<source>/`(适配器)← `api`/命名空间;providers **不得**反向依赖具体命名空间。
- 重试只针对可重试异常,不盲 `except Exception`;限流用 `core.rate_limit`。

---

## 8. 日志规范 🔒

- **库代码不主动配置全局 logging**(不 `basicConfig`、不加 handler);只 `logging.getLogger("probar.<module>")`。
- 级别:
  - `INFO`:请求开始/结束、缓存命中、fallback 发生。
  - `WARNING`:重试、限频、降级、字段缺失。
  - `ERROR`:最终失败、`SchemaChanged`。
- 🔒 **禁止记录** cookie / token / 完整 header / query 中的敏感项(有测试断言)。
- 每条日志含 `source / interface / symbol / request_id`;**不默认打印大响应体**。

---

## 9. 文档与教程规范 🔒

- 站点用 `mkdocs-material`,**按源生成**;每接口标:**支持/不支持/字段(含单位)/限制/质量档**。
- 🔒 能力矩阵与文档接口表**自动校验**:新增接口但未更新 capabilities/docs → CI 失败。
- 教程:`quickstart`(install→第一条 K 线)+ `cookbook`(资金流选股、龙虎榜、批量快照、auto 降级)。
- 🔒 **CHANGELOG 纪律**:非 docs-only 的 PR 必须带 `CHANGELOG.md` 条目(CI 检查)。

---

## 10. Issue 分诊与回复 🔒

- **标签**:`source:dc|tdx|ths`、`type:bug|schema-change|parse-error|feature|docs|question`、`priority:p0|p1|p2|p3`。
  (canary 的 `parse_error` 归 `type:parse-error`,`schema_changed` 归 `type:schema-change`。)
- **SLA**(响应,非修复):
  - **P0** 核心接口全挂 / 发布损坏 → 24h。
  - **P1** 核心接口 schema 变化 → 48h。
  - **P2** 单接口 bug → 7d。
  - **P3** 增强/提问 → 按维护节奏。
- 回复**必须**要齐复现信息:probar 版本、接口、symbol、参数、错误栈、是否稳定复现。模板见 `.github/ISSUE_TEMPLATE/`。
- canary 自动建的 issue 走同一套标签与闭环。

---

## 11. GitHub 项目维护 🔒

- `main` 分支保护:**CI 必过 + 至少一次复核**才能合并;禁止直接 push main。
- 每个 PR 走 `PULL_REQUEST_TEMPLATE.md`,强制勾选:测试/文档/兼容性/canary 影响。
- `Dependabot` 管依赖;破坏性升级走 CI,不自动合并。
- `CODEOWNERS` 指定各 `probar/providers/<source>/` 负责人。
- **重大决策写 ADR**:`docs/adr/ADR-NNNN-*.md`(新 provider、改公共模型、改默认语义)。Roadmap 只维护 1–2 个版本窗口。

---

## 12. pip 发布规范 🔒

**发布固定顺序(每次发版严格按此,不得跳步)**:
1. **本地验证**:`ruff check` + `mypy probar` + `pytest` 全绿(发的就是这次提交的状态)。
2. **推送 GitHub**:push 到 `main`,确认 **GitHub CI 也绿**(本地 + 云端双重验证)。
3. **更新文档**:CHANGELOG 定版(`[Unreleased]` → `[X.Y.Z] + 日期`)、接口表/质量档/README 同步,一并推上去。
4. **PyPI 发布**:打 `vX.Y.Z` tag 触发 `release.yml`,经 Trusted Publishing 自动构建并发布。

- **只走 PyPI Trusted Publishing(OIDC)**,禁止本地手工 `twine upload`。
- 发布前 checklist(`release.yml` 内置 + 人工确认):lint ✓ / mypy ✓ / unit+contract ✓ / 核心 canary ✓ /
  CHANGELOG 与 release notes ✓ / 版本号与 tag 一致 ✓。
- tag 必须从已过 CI 的 commit 打;`vX.Y.Z` 触发 `release.yml`。

---

## 13. 安全与合规 🔒

- 🔒 **禁止提交** token/cookie/密钥;启用 secret scanning;`.gitignore` 覆盖本地缓存与状态。
- 账号权限最小化;发布权限仅给 Trusted Publishing,定期审计。
- 依赖锁定 + 供应链审计(`pip-audit`/Dependabot)。
- **合规边界**:封装非官方/逆向接口,README 免责声明常驻;内置限流做"友好访问";
  **不鼓励、不提供**绕过反爬/封禁的手段;尊重各平台 ToS。

---

## 14. 治理流程

- **ADR/RFC**:新 provider、大改接口、改公共模型/默认值,**先写设计记录**再实现(`docs/adr/`)。
- **可观测性**:canary 历史结果以 JSON artifact 留存;有条件做状态页/dashboard。
- **性能基准**:对 parser 耗时、批量 `quotes`、缓存命中保留基准,防性能回归。
- **社区治理**:维护者权限、PR 合并标准、长期无响应 issue 的关闭规则,随项目成长补充。
- 本宪章每季度 review 一次;修改本身也走 PR + 复核。

---

## 附:执行状态清单(规范 → 门禁)

| 规范 | 落地形式 | 状态 |
|---|---|---|
| ruff / mypy / pytest | `ci.yml` | ✅ 已落地 |
| 单测禁网(`@network` 标记) | pytest 配置 + fixture | ⬜ 待建 |
| parser fixture / 契约测试 | `tests/` | ✅ 部分(东财已覆盖) |
| 能力矩阵 ↔ 方法/文档 一致性校验 | CI 脚本 | ⬜ 待建 |
| CHANGELOG 必带条目 | CI 检查 | ⬜ 待建 |
| 弃用必带 DeprecationWarning 测试 | pytest | ⬜ 待建(暂无弃用) |
| canary 结构化 JSON + 失败分类 + 自动 issue | `canary.yml` + `scripts/canary.py` | 🟡 雏形(分类有,自动 issue 待建) |
| 日志不含敏感信息 | 单测断言 | ⬜ 待建(日志模块待建) |
| 错误模型补 `InvalidSymbol`/`ParseError` | `probar/core/errors.py` | ⬜ 待建(minor) |
| 发布 Trusted Publishing + checklist | `release.yml` | ✅ 已落地 |
| Issue/PR 模板 | `.github/ISSUE_TEMPLATE/` + `PULL_REQUEST_TEMPLATE.md` | ✅ 已落地 |
| Issue 必填复现字段 | issue 模板强制 | ✅ 已落地 |
| 安全策略 / 漏洞上报 | `SECURITY.md` | ✅ 已落地 |
| `CODEOWNERS`(各 provider 负责人) | `.github/CODEOWNERS` | ⬜ 待建(需 GitHub 账号) |
| 禁提交密钥 + secret scanning | `.gitignore` + 仓库设置 | 🟡 .gitignore 已覆盖;扫描待开 |
| 依赖 / 供应链审计 | `pip-audit` + Dependabot | ⬜ 待建 |
| `main` 分支保护(CI 必过 + 复核) | 仓库设置 | ⬜ 待建(需 GitHub 权限) |
| ADR 流程 | `docs/adr/` | ⬜ 待建 |
| 文档站 | mkdocs | ⬜ 待建 |

> 「待建」项即总工程师的**近期施工清单**,按 v0.2/v0.3 节奏纳入。规范先行,实现逐条对齐。
