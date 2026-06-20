# 同花顺 `pb.ths`

**实验性(v0.3,`pip install "probar[ths]"`)**。同花顺走 Web 接口 + 反爬(`hexin-v` 等),
**长期稳定性不保证**,因此**不进核心行情主链路**。它的独特价值在:

- `wencai` —— **问财自然语言选股**(如 `"近5日主力净流入为正且市值<100亿"`),同花顺独有。
- `concept / concept_cons`、`industry / industry_cons` —— 业界最细的**概念 / 题材分类**。
- `quote`、`f10`、`lhb` —— 其它增强数据。

当前均为占位,调用抛 `NotImplementedError`。

!!! warning "best-effort"
    反爬接口随时可能失效;它的能力在 [能力矩阵](../reference/capabilities.md) 中标为 ⚠️。
    高频行情请用 `pb.dc` / `pb.tdx`,把 `pb.ths` 当"题材增强源"。
