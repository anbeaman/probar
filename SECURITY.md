# 安全策略

## 上报漏洞

请**不要**在公开 Issue 中提交安全问题。通过 GitHub 的私密上报(Security → Report a vulnerability)
或邮件联系维护者私下沟通。我们会在确认后尽快修复并致谢。

## 支持的版本

仅最新的 minor 版本接受安全修复;旧版本请升级。

## 使用者须知

- probar 封装的是各平台**非官方/逆向**接口,仅供学习研究;请遵守各平台 ToS(见 README 免责声明)。
- 本库**不收集**任何凭证;若你为同花顺等源传入 cookie,请自行妥善保管,**切勿**提交到仓库或 Issue。

## 贡献者须知(硬性)

- **禁止提交** token / cookie / 密钥 / 完整敏感请求头;`.gitignore` 已覆盖本地缓存与状态目录。
- 日志与异常信息**不得**包含上述敏感数据(见 `docs/ENGINEERING_GUIDE.md` §8 日志规范)。
- 发布权限仅通过 PyPI Trusted Publishing(OIDC),不使用长期 API Token。
