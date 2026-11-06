# Mika 独立镜像

本仓库为 `KUAILESHANGWEI/mika`，独立于上游 Fork 网络。上游作者及许可证归属保持原样。

- 每小时第 23 分钟运行 Independent mirror，也可在 Actions 手动运行。
- 上游分支保存在 `upstream/*`，标签及完整 Git 历史保留。`main` 合并上游默认分支，并重新应用下载、文档及应用更新地址本地化。
- 上游最新 Release 的全部附件按原字节归档在 `upstream-v*` 预发布中，校验大小和 SHA-256。历史归档不会因上游删除而清理。
- 正式 Release 使用 `v版本+mirror` 标签，指向本地化后的源码，并发布基于对应上游版本构建的独立签名 APK，应用更新地址为本仓库。原版 APK 的内部地址无法通过单纯复制附件改变，因此原版与独立版分开归档。
- 独立签名保存在仓库 Actions Secrets 中，跨版本保持一致。独立版无法直接覆盖上游签名的已安装版本，迁移前先备份数据。
- 同步使用默认 `GITHUB_TOKEN`。用户已选择接受其权限限制：上游修改 `.github/workflows/` 文件时，GitHub 可能拒绝推送，对应 Actions 会报错，需要单独处理后继续同步。
- 上游不可用时，已有代码、归档和已发布安装包继续保留。上游恢复后继续同步。合并冲突或校验失败会使 Actions 报错，并保留已发布状态。
- 手机模型服务、账号和网络仍需使用者自行配置。第三方软件许可证、鸣谢和外部服务地址保留。

下载独立版请打开 https://github.com/KUAILESHANGWEI/mika/releases/latest 。
