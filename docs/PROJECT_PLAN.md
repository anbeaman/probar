# probar 项目总体方案(运维 / 发布 / 演进手册)

> 本文件是 probar 的**总体执行方案**,与 [`ENGINEERING_GUIDE.md`](ENGINEERING_GUIDE.md)(原则/约束)互补:
> 前者讲"怎么运维、怎么发布、怎么演进",后者讲"必须守的规矩"。两者冲突时以 ENGINEERING_GUIDE 的 🔒 条款为准。
> 维护者据此长期执行,保证项目**稳定可靠运行 + 及时更新部署**。

---

## 1. 项目定位与非目标

- **定位**:稳定、可观测的 **A 股数据接入层**,按数据源拆独立命名空间,把三源数据**统一、可靠**地喂出来。
- **核心价值**:不是"接口最多",而是**接口坏了能最快发现、最快修、用户最少踩坑**。
- **非目标**:不做回测/策略引擎(交给 backtrader/vnpy);不做付费/鉴权数据(L2、Choice);不绕过任何访问控制。
- **铁律**:各源数据**各自独立、口径可能不一致**,按需选源,**不做"主源"、不做跨源故障转移/替换**。
  每个源各自把自己的接口做全——别家有了也不省(用户要看的是"那个软件"的数据)。

## 2. v0.1.0 稳定发布范围(冻结)

**只有以下已实现接口属于 v0.1.0 公共稳定承诺**(参数名/核心列/单位/异常类型按稳定 API 对待):

| 命名空间 | 接口 |
|---|---|
| `pb.dc`(东方财富,HTTP/JSON) | `quote` / `quotes` / `kline` / `intraday` / `fund_flow` / `lhb` / `financials` / `securities` |
| `pb.tdx`(通达信,clean-room 二进制协议) | `quotes` / `quote` |

**不属于 v0.1.0 稳定承诺**:所有 `NotImplementedError` 占位接口、`pb.ths` 全部、路线图项。
它们在命名空间里**仅声明**(诚实反映能力),文档须明确标注"规划中,非稳定 API"。

**发版前三项补强**(不新增接口):① 修 `dc.kline` 的 `limit` 失效;② `dc.securities` 接 TTL 缓存;③ 限流/非官方接口风险写清。
**待验证可选项**:`dc.quotes` 改 push2 批量(`ulist`)以缓解分页限频——实测可靠则进 v0.1.0,否则留 v0.2。

## 3. 架构方案

- **分层**:`命名空间(pb.dc/tdx/ths)` → `provider client` → `传输层` → `纯函数 parser` → `统一 schema`。
- **传输层按源异构**:
  - 东财:`core/http.py`(httpx,超时/限流/退避重试),HTTP/JSON。
  - 通达信:`providers/tdx/_protocol.py` + `_codec.py`(**纯标准库 socket/struct/zlib,clean-room 自写二进制协议,零第三方依赖**),
    `transport.py` 持有服务器池 + 业务探针 + 失败降级换服务器。
- **共享 core**:`errors`(结构化异常)、`symbols`(代码归一)、`rate_limit`(TokenBucket)、`cache`(TTLCache)、
  `calendar`、`models`(列契约)、`capabilities`(能力矩阵**参考**,非路由表)。
- **纯函数 parser**:输入已解析数据、输出 DataFrame/dict,无网络 → 可用冻结 fixture 做确定性离线单测。

## 4. 数据源与接口治理

- **能力矩阵**(`pb.capabilities()`)是**各源能力参考**,不是方法清单、不做路由。
- **接口面诚实**:某源没有的数据域(如 TDX 无资金流/龙虎榜)→ 命名空间里**不存在该方法**(`AttributeError`),不是运行时"不支持"。
- **跨源列契约**:同名接口返回**统一核心列**(形状一致,便于切换);源特有稳定字段作为额外**列**(文档登记单位)。
  注意:列名一致 ≠ 数值一致,各源数据独立。

## 5. 维护方案(日常稳定运行)

- **canary 两层**:GitHub Actions 仅 **soft smoke**(境外 runner 对国内接口会误报,只作噪声参考);
  **国内节点**(云函数/VPS)做**主巡检**,出 `schema/data` 硬失败时自动开 Issue。
- **频率**:核心接口**交易日每日**一次;低频重接口 **weekly**;**发版前**手动跑一次完整 canary。
- **失败分类**:`network / ratelimit / nodata / schema_changed / parse_error / data_anomaly`。
  其中 `schema_changed` / `parse_error` = 真信号 → 进热修流程;`network/ratelimit` = soft,不算硬失败。
- **canary 自身纪律**:失败信息**截断**(不打整列/大响应体);对前复权负价等"真实但反直觉"的数据用合理判据,避免误报。

## 6. 部署与发布方案

- **CI**(`ci.yml`):push/PR 跑 ruff + mypy + pytest(禁网)。**只从 CI 已绿的 commit 打 tag**。
- **发布**(`release.yml`):打 `vX.Y.Z` tag → 触发 → PyPI **Trusted Publishing(OIDC)**,`pypa/gh-action-pypi-publish`。
- **发布门禁清单(release checklist)** —— 逐项过,缺一不发:
  1. `probar/_version.py` == 目标版本;tag == `v<版本>`;
  2. `CHANGELOG.md` 从 `Unreleased` 定版为 `[X.Y.Z] - 日期`;
  3. README/docs/capabilities **不把未实现接口宣传为稳定能力**;
  4. `ruff check probar tests scripts` / `mypy probar` / `pytest` 全绿;
  5. `python -m build` 成功,从 wheel 安装后 `import probar; probar.__version__` 正确;
  6. `mkdocs build --strict` 通过;
  7. 国内网络跑 `scripts/canary.py`,**只允许已解释的 network/ratelimit soft 失败**;出 schema/data 不发;
  8. PyPI Trusted Publishing 的 owner/repo/workflow/environment 与 `release.yml` 一致;
  9. tag 发布后**不改写**。
- **回滚预案**:PyPI **同版本号不可重传**。坏包已发 → **yank** 该版本(非破坏性、用户已装不受影响)+ 立即发 **patch(0.1.1)** 热修;
  源站临时不可用 → 不 yank,标 degraded、补文档或发 patch。
- **隐私铁律**(发布到云端务必遵守):**绝不**上云 ① 与用户的对话内容 ② 任何本地开发/协作工具及其配置与相关字样 ③ 个人敏感信息。
  commit 用中性信息、**不加 Co-Authored-By**;git 作者 = `anbeaman <anbeaman@users.noreply.github.com>`。

## 7. 接口更新方案(新接口接入流水线)

每个新接口按"标杆"流水线落地,缺一不补全不算完成:

1. **实网探针**:连真实源拿一次真实响应;
2. **冻结 fixture**:把脱敏真实响应存为 `tests/fixtures/*`;
3. **纯函数 parser**:解析 + 错误分档(`NoData`/`SchemaChanged`/...);
4. **client 方法**:参数校验 + 限流 + 归一化 + 溯源 `df.attrs`;
5. **能力矩阵 / 文档**:登记字段/单位/示例/注意;
6. **离线测试**:解析 + 列契约 + 分页/边界,走禁网门禁;
7. **canary 探针**:实网巡检 + 合理性校验;
8. **CHANGELOG**:记一条。

## 8. 缺陷修复与热修方案

- **触发**:canary 报 `schema_changed`/`parse_error`,或用户 Issue。
- **流程**:保存脱敏真实响应 → 加 fixture(复现)→ 修 parser/client → **加回归测试** → 更新 CHANGELOG → 发 `patch`(0.1.1)。
- **优先级**:数据正确性 > 可用性 > 性能 > 体验。`SchemaChanged` 视为头号信号,优先热修。

## 9. 文档方案

- **mkdocs-material**,按源生成;每接口标:**参数 / 返回字段(含单位)/ 示例 / 注意 / 是否稳定**。
- **限流/频率如实**(三层,不暗示官方配额):
  - 已实现事实:probar 默认 `rate=10.0`(客户端令牌桶限制**发出**速度);
  - 使用建议(**经验值**):批量历史/财务/龙虎榜建议 1–3 req/s;`securities` 建议缓存后低频调用;
    TDX 批量优先用 `quotes` 分批,不要单只循环;
  - 免责声明:**"默认限流是 probar 的友好访问保护,不是数据源承诺的 SLA 或官方配额"**;不同 IP/时段/endpoint 表现可能不同。
- 发布前 `mkdocs build --strict` 必须通过。

## 10. 版本策略与兼容承诺(SemVer)

- 虽为 `0.x`,**v0.1.0 已实现接口**的参数名、核心列名、单位、异常类型**按稳定 API 对待**。
- **patch(0.1.x)**:bug / schema 热修,不改公共契约;
- **minor(0.x.0)**:新增接口/源;
- **破坏性**(删列、改默认语义、改单位):必须显式标注 + 走 minor(0.x)或 major(≥1.0)。
- `df.attrs`(`source`/`provenance`/`schema_version`/`server` 等)**不是稳定业务契约**,仅作调试溯源,不承诺向后兼容。

## 11. 风险清单与应对

| 风险 | 应对 |
|---|---|
| **规划/stub 接口被当成稳定 API** | 发布前把稳定范围写死(§2);文档明确标"规划中,非稳定";stub 调用抛 `NotImplementedError` 注明计划版本 |
| **缓存 DataFrame 被原地改写污染缓存** | `dc.securities` 等接 TTL 时**存取都 `.copy(deep=True)`**,**不缓存异常** |
| 上游字段漂移(SchemaChanged) | parser 严格分档 + canary 头号目标 + 热修流程 |
| 东财网页分页限频 | 慢变数据 TTL 缓存;批量端点(P1);限流 + 退避;不靠跨源替代 |
| TDX 服务器不稳 | 服务器池 + 业务探针 + 失败降级换服务器;canary 定期复验淘汰 |
| 实网测试在境外 runner 误报 | canary 分两层;CI 只 soft smoke;主巡检在国内节点 |
| 发布不可逆 | 门禁清单 + yank/patch 回滚预案 |

## 12. 东财更优接入(公开渠道,演进方向)

只走**公开、免鉴权、不绕访问控制**的路子(L2/Choice 涉付费鉴权,**不做**):

- **P1**:`dc.quotes` 改 push2 批量(`ulist`/`ulist.np` 的 `secids`),把"N 次单只"降到 1–2 次 → 直击分页限频。先实测最大批量再分批(50/80)。
- **P2**:datacenter 统一**分页 helper**(按 `total` 拉全,防静默截断),不依赖超大 `pageSize`。
- **P3**:`clist` 的 `pz` 调优(接 TTL 后收益下降,低优先)。
- **暂不做 WebSocket**:除非证明有公开、免鉴权、不绕访问控制、可长期稳定的接口。实时优先靠 HTTP 批量 + TDX TCP。

## 13. 决策记录(ADR-lite)

格式:日期 · 争议点 · 选项 · 最终决定 · 理由。

- **2026-06-21 · TDX 传输策略** · 依赖 pytdx / clean-room 自写 · **clean-room 自写(纯标准库零依赖)** · 用户拍板;参考 pytdx 协议事实重写、不照抄代码,pytdx 仅作 dev oracle。
- **2026-06-21 · 跨源故障转移与主源** · 保留 pb.auto / 删除 · **删除,各源独立不替换** · 用户拍板;不同软件数据不重合,用户要看特定源。
- **2026-06-21 · v0.1.0 接口范围** · 含 tdx.securities / 收口 · **收口:dc 8 + tdx quotes/quote,tdx.securities 留 v0.2** · 交叉复核建议、维护者采纳;第一版卖"已实现可信",不卖"路线图满"。
- **2026-06-21 · dc.quotes 批量优化** · 进 v0.1.0 / 留 v0.2 · **已实网验证可靠 -> 进 v0.1.0** · 维护者定;直击分页限频痛点。
- **2026-06-21 · 限流/频率表述** · · **写成"保守经验值 + 非官方配额"三层免责** · 交叉复核提示、维护者采纳;避免被当成保证。
- **2026-06-21 · tdx.securities 北交所** · 拉 BJ / 不拉 · **只覆盖沪深(BJ 经 TDX 不稳、失败要 ~27s),北交所用 `pb.dc.securities`** · 维护者定;各源独立,`coverage=SH+SZ` 透明标注。
- **2026-06-21 · tdx.kline 复权** · 自算 qfq/hfq / 仅原始价 · **v0.3 仅原始价(adjust=None);qfq/hfq 抛 NotSupported,待 xdxr** · 维护者定;TDX 不直接给复权,先发可信原始价,复权随 xdxr 落地。
- **2026-06-21 · xdxr/复权分步** · 一步到位(含复权)/ 分步 · **分步:v0.4 只做 tdx.xdxr 事件表(与 pytdx 逐值零不符、可精确验证);复权(qfq/hfq 接 kline)下一轮单独做** · 维护者定;复权无精确 oracle、因子公式易错,单独一轮更稳。
- **2026-06-21 · 自主迭代模式** · · **用户授权:不说停就持续迭代,经交叉复核定方案、记录、自己拍板,不逐个征询** · 用户拍板;每轮小而可验证、交叉复核终审后发版。
