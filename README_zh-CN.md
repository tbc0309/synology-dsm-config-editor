# Synology DSM 配置编辑器——简体中文

[English](README.md)

这是一个用于 Synology DSM 7 套件的无依赖 Shell CGI 配置文件编辑器。本分支固定使用简体中文界面。

![界面预览](docs/images/configuration-editor-preview.png)

## 两种版本

仓库提供两个版本，编辑、保存、安全校验、三份备份、端口读取和重启功能完全一致：

- `main`：多语言版。按照 DSM 官方 `texts` 语言设置切换，包含 21 个编辑器语言包，无对应翻译时回退英文。
- `zh_cn`：简体中文版。界面固定为简体中文，不包含 `texts`、`i18n` 和语言切换逻辑。

面向其他开发者发布或需要适配不同 DSM 语言时选择 `main`；只需要固定中文界面时选择 `zh_cn`。不要混用两个分支中的 UI 文件。

## 功能

- DSM Cookie 登录验证，支持 `admin` 和 `authenticated` 权限模式
- 读取、编辑、保存、重新读取、行号和光标位置
- TOML、YAML、JSON、INI、env、Shell 轻量语法高亮
- 轮换保留三份备份，`.bak.1` 最新
- 原子保存锁和同目录临时文件替换
- 固定服务端口，或从配置文件指定键读取数字端口
- 只读“打开服务”按钮，可附加访问路径
- 显示套件状态，保存后可执行 `start-stop-status stop`、`start`
- 2 MiB 限制、CSP、同源保存校验和 HTML 转义

## 文件职责

```text
ui/
├─ config          DSM 桌面注册：应用 ID、标题、图标、版本
├─ Main.js         DSM 窗口类和 iframe 地址
├─ gettoken.html   打开编辑器前获取 SynoToken
├─ index.cgi       编辑器页面和读写接口
├─ editor.conf     套件配置路径、端口、权限和重启方式
└─ images/         16–256 像素 DSM 桌面图标
```

`index.cgi` 和 `gettoken.html` 是通用文件。用于其他套件时，必须修改下面这些套件专用文件。

## 1. 修改 `ui/editor.conf`

仓库保留 EasyTier 参数作为完整样板：

```ini
PACKAGE_NAME=EasyTier
CONFIG_FILE=/var/packages/EasyTier/var/config.toml
DEFAULT_PORT=
PORT_CONFIG_KEY=
OPEN_PATH=/
ACCESS_MODE=admin
RESTART_MODE=lifecycle
RESTART_SCRIPT=
RESTART_ARGS=
```

- `PACKAGE_NAME`：必须与 SPK `INFO` 中的套件名完全一致。
- `CONFIG_FILE`：普通配置文件的绝对路径，不支持符号链接。
- `DEFAULT_PORT`：可选固定数字端口。留空时，除非 `PORT_CONFIG_KEY` 成功读取端口，否则隐藏“打开服务”。
- `PORT_CONFIG_KEY`：可选，例如 `webServer.port`。支持常见的 `key = 7500`、`key = "7500"`、`key: 7500` 和引号形式。
- `OPEN_PATH`：端口后的路径，例如 `/` 或 `/xxx.html`，必须以 `/` 开头。
- `ACCESS_MODE`：可选 `admin` 或 `authenticated`。
- `RESTART_MODE`：可选 `lifecycle`、`script`、`none`。
- `lifecycle`：执行 `/var/packages/<PACKAGE_NAME>/scripts/start-stop-status stop`，然后执行 `start`。
- `script`：执行服务器端指定的 `RESTART_SCRIPT` 和 `RESTART_ARGS`。

## 2. 修改 `ui/config`

保留 JSON 结构，替换 EasyTier 类名、标题、描述、图标路径和版本。

`version` 必须按照 SPK `INFO` 中的程序版本填写，不能固定成编辑器自己的版本。`INFO` 中的 `dsmappname` 必须和应用 ID 对应，例如 `SYNO.SDS.EasyTier.Instance`。

```json
{
    "Main.js": {
        "SYNO.SDS.EasyTier.Instance": {
            "type": "app",
            "version": "1.3.0",
            "desc": "EasyTier",
            "icon": "images/icon_{0}.png",
            "title": "EasyTier",
            "allowMultiInstance": false,
            "appWindow": "SYNO.SDS.EasyTier.Main",
            "depend": []
        },
        "SYNO.SDS.EasyTier.Main": {
            "type": "lib",
            "title": "EasyTier",
            "icon": "images/icon_{0}.png",
            "depend": []
        }
    }
}
```

## 3. 修改 `ui/Main.js`

把以下 EasyTier 标识全部替换成新套件的类名和路径：

```text
SYNO.SDS.EasyTier.Instance
SYNO.SDS.EasyTier.Main
/webman/3rdparty/EasyTier/gettoken.html
```

类名必须与 `ui/config`、SPK `INFO` 对应；`/webman/3rdparty/<名称>/` 必须与套件实际安装的网页映射一致。

## 4. 替换 `ui/images`

替换整套图标，但保持以下文件名：

```text
icon_16.png   icon_24.png   icon_32.png   icon_48.png
icon_64.png   icon_72.png   icon_96.png   icon_128.png
icon_256.png
```

发布其他套件时不要继续使用 EasyTier 图标。

## 安装要求

- 将完整 `ui` 目录安装到套件 target。
- 映射到 `/webman/3rdparty/<套件>/`。
- 给 CGI 执行权限：

```sh
chmod 755 /var/packages/YourPackage/target/ui/index.cgi
```

- 套件账户必须能读写配置文件所在目录。
- lifecycle 模式还必须能控制套件自己的进程。

## 检查清单

- `INFO package`、`INFO dsmappname`、`ui/config`、`Main.js` 标识一致。
- `ui/config` 版本与 SPK 程序版本一致。
- `editor.conf` 指向正确的套件和配置文件。
- 图标属于当前套件。
- 配置目录权限允许创建备份和临时文件。
- 在 DSM 上测试退出登录、普通用户、管理员、保存、备份、状态和重启。

## 注意

- 除非普通登录用户确实需要编辑配置，否则保持 `ACCESS_MODE=admin`。
- 保存前不会校验 TOML、YAML 等配置语法。
- 重启失败不会撤销已经成功保存的内容。
- 如果 DSM 在保存过程中强制终止 CGI，需要手工删除配置文件旁隐藏的 `.editor.lock` 目录。

安全边界见 [SECURITY_zh-CN.md](SECURITY_zh-CN.md)。
