# 跨源故障转移 `pb.auto`

可选的跨源路由,**默认不参与任何调用**——只有显式调用 `pb.auto.*` 才会启用。
按 `prefer` 顺序依次尝试,成功即返回,并在 `df.attrs` 标注**真实来源**与降级原因。

```python
df = pb.auto.kline("000001.SZ", prefer=["dc", "tdx"])
df.attrs["source"]            # 实际命中的源
df.attrs.get("fallback_reason")  # 若发生降级,记录前面源失败的原因
```

支持:`kline`、`quote`(随各源实现推进而增加)。

!!! warning "为什么默认不开"
    不同源的口径不完全一致(复权口径、时间戳边界、字段覆盖)。`auto` **绝不静默降级**:
    它只在 `网络错误 / 限频 / 不支持 / 未实现` 时切换,而 `SchemaChanged` / `NoData` 会**直接抛出**
    —— 避免用另一个源的数据掩盖问题、造成不可解释的回测差异。
