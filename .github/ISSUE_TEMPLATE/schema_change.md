---
name: 接口失效 / Schema 变更
about: 上游接口字段变了、解析失败、canary 报警(SchemaChanged / ParseError)
title: "[schema] "
labels: ["type:schema-change"]
---

<!-- canary 自动建的 issue 也用此模板。请打上 source:dc / source:tdx / source:ths。 -->

## 受影响接口
<!-- 如 pb.dc.kline -->

## 失败类型
- [ ] schema_changed(字段/结构变了) · [ ] parse_error(解析失败) · [ ] provider_down

## 证据
- 报错(`SchemaChanged` / `ParseError`)信息:
- 发生时间 / 频率:
- **脱敏**响应摘要(务必去掉 cookie/token/敏感头):
```json

```

## 修复路径(维护者填)
- [ ] 用真实响应更新 fixture
- [ ] 改 parser/endpoint
- [ ] 加回归测试
- [ ] 发 patch 版
