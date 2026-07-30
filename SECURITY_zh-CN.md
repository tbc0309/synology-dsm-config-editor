# 安全说明

## 已有保护

- 使用群晖官方 `authenticate.cgi` 验证 DSM Cookie
- 默认只允许 DSM `administrators` 组
- 配置路径和命令只来自服务器端 `editor.conf`
- 保存必须使用 POST、`text/plain`、`X-Requested-With` 和同源请求信号
- 文件和请求最大 2 MiB
- 禁用 Shell 文件名通配符，不使用 `eval` 或 `sh -c`
- 使用原子锁、私有临时文件、三份备份和同目录替换
- 替换文件时保留原数字 UID、GID 和 mode
- 语法高亮前转义配置内容
- 页面发送 CSP、`nosniff`、`no-referrer`、`no-store`

## 安全边界

- 非空 `SynoToken` 只是请求约束，身份仍由 DSM Cookie 验证。
- `ACCESS_MODE=authenticated` 会允许所有已登录 DSM 用户读取、保存并触发配置的保存后操作。
- `CONFIG_FILE` 必须是普通文件，不能是符号链接。
- 无依赖 Shell 方案不能通用保留 ACL 和扩展属性。
- `lifecycle` 会直接执行套件自己的 `start-stop-status`，套件账户权限必须兼容。
- `script` 模式信任服务器端指定的 `RESTART_SCRIPT`。
- 编辑器不校验配置语法，也不检测端口冲突。
- DSM 7 套件应尽量使用低权限 package 账户运行。

## 部署检查

请在目标 DSM 上测试：退出登录、普通用户、保存、三份备份、重启失败和并发保存。

安全问题请私下联系仓库所有者。
