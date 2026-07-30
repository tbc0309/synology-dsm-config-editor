#!/bin/sh

# Generic, dependency-free configuration editor for Synology DSM.
# Put per-package settings in "editor.conf" beside this CGI.

# Disable pathname expansion so trusted RESTART_ARGS cannot accidentally expand
# wildcard characters into filenames.
set -f

SCRIPT_PATH=${SCRIPT_FILENAME:-$0}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")" 2>/dev/null && pwd)
SETTINGS_FILE="${SCRIPT_DIR}/editor.conf"
MAX_BYTES=2097152
AUTH_CGI=/usr/syno/synoman/webman/modules/authenticate.cgi

json_error() {
    status="$1"
    message="$2"
    # DSM replaces non-2xx CGI responses with its own HTML error page, hiding
    # the useful message. Keep HTTP 200 and carry the original status in JSON.
    printf 'Content-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nX-Editor-Error: 1\r\n\r\n'
    escaped=$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')
    escaped_status=$(printf '%s' "$status" | sed 's/\\/\\\\/g; s/"/\\"/g')
    printf '{"ok":false,"status":"%s","message":"%s"}\n' "$escaped_status" "$escaped"
    exit 0
}

authenticate_request() {
    [ -x "$AUTH_CGI" ] ||
        json_error '500 Internal Server Error' 'DSM authentication helper is unavailable'
    # Synology documents this helper for third-party CGI authentication. It
    # inherits the request cookie and network environment from this CGI.
    AUTH_USER=$("$AUTH_CGI" 2>/dev/null | tr -d '\r\n')
    [ -n "$AUTH_USER" ] || json_error '401 Unauthorized' 'DSM login is required'
    case "$AUTH_USER" in
        *[!A-Za-z0-9._@-]*) json_error '403 Forbidden' 'Invalid DSM user identity' ;;
    esac
}

setup_lifecycle_env() {
    package_root="/var/packages/${PACKAGE_NAME}"
    dsm_major=$(synogetkeyvalue /etc.defaults/VERSION majorversion 2>/dev/null)
    case "$dsm_major" in ''|*[!0-9]*) dsm_major=7 ;; esac
    export SYNOPKG_PKGNAME="$PACKAGE_NAME"
    export SYNOPKG_DSM_VERSION_MAJOR="$dsm_major"
    export SYNOPKG_PKGDEST="${package_root}/target"
    export SYNOPKG_PKGVAR="${package_root}/var"
    export SYNOPKG_PKGETC="${package_root}/etc"
    export SYNOPKG_USERNAME="$AUTH_USER"
    export SYNOPKG_DSM_LANGUAGE="$REQUESTED_LANG"
}

validate_save_request() {
    [ "${REQUEST_METHOD:-}" = "POST" ] ||
        json_error '405 Method Not Allowed' '保存必须使用 POST'
    case "${CONTENT_TYPE:-}" in
        text/plain|text/plain\;*) ;;
        *) json_error '415 Unsupported Media Type' '保存内容必须使用 text/plain' ;;
    esac
    # Requiring a non-CORS-safelisted header prevents a third-party page from
    # submitting a simple cross-origin form POST. Origin and Fetch Metadata are
    # retained as defense in depth for modern DSM browsers.
    [ "${HTTP_X_REQUESTED_WITH:-}" = "XMLHttpRequest" ] ||
        json_error '403 Forbidden' '拒绝缺少请求标识的保存请求'
    case "${HTTP_SEC_FETCH_SITE:-}" in
        cross-site) json_error '403 Forbidden' '拒绝跨站保存请求' ;;
    esac
    if [ -n "${HTTP_ORIGIN:-}" ] && [ -n "${HTTP_HOST:-}" ]; then
        case "$HTTP_ORIGIN" in
            "http://${HTTP_HOST}"|"https://${HTTP_HOST}") ;;
            *) json_error '403 Forbidden' '拒绝跨来源保存请求' ;;
        esac
    elif [ -n "${HTTP_REFERER:-}" ] && [ -n "${HTTP_HOST:-}" ]; then
        case "$HTTP_REFERER" in
            "http://${HTTP_HOST}/"*|"https://${HTTP_HOST}/"*) ;;
            *) json_error '403 Forbidden' '拒绝来源不明的保存请求' ;;
        esac
    fi
}

get_setting() {
    key="$1"
    sed -n -e 's/\r$//' -e "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$SETTINGS_FILE" | sed -n '1p'
}

load_settings() {
    [ -r "$SETTINGS_FILE" ] || json_error '500 Internal Server Error' '找不到 editor.conf'
    CONFIG_FILE=$(get_setting 'CONFIG_FILE')
    DEFAULT_PORT=$(get_setting 'DEFAULT_PORT')
    PORT_CONFIG_KEY=$(get_setting 'PORT_CONFIG_KEY')
    OPEN_PATH=$(get_setting 'OPEN_PATH')
    PACKAGE_NAME=$(get_setting 'PACKAGE_NAME')
    ACCESS_MODE=$(get_setting 'ACCESS_MODE')
    RESTART_MODE=$(get_setting 'RESTART_MODE')
    RESTART_SCRIPT=$(get_setting 'RESTART_SCRIPT')
    RESTART_ARGS=$(get_setting 'RESTART_ARGS')
    case "$CONFIG_FILE" in
        /*) ;;
        *) json_error '500 Internal Server Error' 'CONFIG_FILE 必须填写绝对路径' ;;
    esac
    case "$PORT_CONFIG_KEY" in
        ''|*[!A-Za-z0-9_.-]*) PORT_CONFIG_KEY='' ;;
    esac
    if [ -z "$DEFAULT_PORT" ] && [ -n "$PORT_CONFIG_KEY" ] && [ -r "$CONFIG_FILE" ]; then
        DEFAULT_PORT=$(awk -v wanted="$PORT_CONFIG_KEY" '
            function trim(value) {
                gsub(/^[ \t]+|[ \t]+$/, "", value)
                return value
            }
            function unquote(value, first, last, single_quote) {
                value=trim(value)
                if (length(value) < 2) return value
                first=substr(value, 1, 1)
                last=substr(value, length(value), 1)
                single_quote=sprintf("%c", 39)
                if ((first == "\"" && last == "\"") ||
                    (first == single_quote && last == single_quote)) {
                    return substr(value, 2, length(value)-2)
                }
                return value
            }
            {
                line=$0
                sub(/\r$/, "", line)
                equals_pos=index(line, "=")
                colon_pos=index(line, ":")
                if (equals_pos && colon_pos) {
                    pos=(equals_pos < colon_pos ? equals_pos : colon_pos)
                } else {
                    pos=(equals_pos ? equals_pos : colon_pos)
                }
                if (!pos) next
                key=unquote(substr(line, 1, pos-1))
                if (key != wanted) next
                value=substr(line, pos+1)
                sub(/[ \t]*#.*/, "", value)
                sub(/[ \t]+;.*/, "", value)
                sub(/[ \t]+\/\/.*/, "", value)
                sub(/[ \t]*,[ \t]*$/, "", value)
                print unquote(value)
                exit
            }
        ' "$CONFIG_FILE")
    fi
    case "$DEFAULT_PORT" in
        ''|*[!0-9]*) DEFAULT_PORT='' ;;
        *) [ "$DEFAULT_PORT" -ge 1 ] && [ "$DEFAULT_PORT" -le 65535 ] || DEFAULT_PORT='' ;;
    esac
    [ -n "$OPEN_PATH" ] || OPEN_PATH='/'
    case "$OPEN_PATH" in
        /*) ;;
        *) json_error '500 Internal Server Error' 'OPEN_PATH 必须以 / 开头' ;;
    esac
    case "$RESTART_MODE" in
        lifecycle|script|none|'') ;;
        *) json_error '500 Internal Server Error' 'RESTART_MODE 只能是 lifecycle、script 或 none' ;;
    esac
    [ -n "$ACCESS_MODE" ] || ACCESS_MODE=admin
    case "$ACCESS_MODE" in
        admin)
            user_groups=$(id -Gn "$AUTH_USER" 2>/dev/null)
            case " $user_groups " in
                *' administrators '*) ;;
                *) json_error '403 Forbidden' 'DSM administrator access is required' ;;
            esac
            ;;
        authenticated) ;;
        *) json_error '500 Internal Server Error' 'ACCESS_MODE must be admin or authenticated' ;;
    esac
    if [ "$RESTART_MODE" = 'lifecycle' ]; then
        case "$PACKAGE_NAME" in
            ''|*[!A-Za-z0-9._-]*) json_error '500 Internal Server Error' 'PACKAGE_NAME 包含无效字符' ;;
        esac
    fi
}

authenticate_request

# Parse only the two query fields used by this CGI. Values are never evaluated.
ACTION=''
HAS_TOKEN=false
REQUESTED_LANG=enu
old_ifs=$IFS
IFS='&'
for query_part in ${QUERY_STRING:-}; do
    case "$query_part" in
        action=*) ACTION=${query_part#action=} ;;
        SynoToken=?*) HAS_TOKEN=true ;;
        lang=enu|lang=chs|lang=cht|lang=krn|lang=ger|lang=fre|lang=ita|lang=spn|lang=jpn|lang=dan|lang=nor|lang=sve|lang=nld|lang=rus|lang=plk|lang=ptb|lang=ptg|lang=hun|lang=trk|lang=csy)
            REQUESTED_LANG=${query_part#lang=}
            ;;
    esac
done
IFS=$old_ifs

case "$ACTION" in
    load|meta|save|status)
        [ "$HAS_TOKEN" = true ] || json_error '403 Forbidden' '请求缺少 SynoToken'
        ;;
esac

if [ "$ACTION" = "load" ]; then
    load_settings
    [ -f "$CONFIG_FILE" ] || json_error '404 Not Found' '配置文件不存在'
    [ -r "$CONFIG_FILE" ] || json_error '403 Forbidden' '没有读取配置文件的权限'
    size=$(wc -c < "$CONFIG_FILE" | tr -d ' ')
    [ "$size" -le "$MAX_BYTES" ] || json_error '413 Payload Too Large' '配置文件超过 2 MiB 限制'
    printf 'Content-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n'
    cat -- "$CONFIG_FILE"
    exit 0
fi

if [ "$ACTION" = "meta" ]; then
    load_settings
    lower_name=$(basename -- "$CONFIG_FILE" | tr '[:upper:]' '[:lower:]')
    case "$lower_name" in
        *.toml) editor_language='toml' ;;
        *.yaml|*.yml) editor_language='yaml' ;;
        *.json|*.jsonc) editor_language='json' ;;
        *.ini|*.conf|*.cfg|*.properties) editor_language='ini' ;;
        .env|*.env) editor_language='env' ;;
        *.sh|*.bash|*.zsh) editor_language='shell' ;;
        *) editor_language='generic' ;;
    esac
    printf 'Content-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\n\r\n'
    escaped_open_path=$(printf '%s' "$OPEN_PATH" | sed 's/\\/\\\\/g; s/"/\\"/g')
    printf '{"ok":true,"defaultPort":"%s","openPath":"%s","restartEnabled":%s,"statusEnabled":%s,"language":"%s"}\n' \
        "$DEFAULT_PORT" "$escaped_open_path" \
        "$([ "$RESTART_MODE" = lifecycle ] || [ "$RESTART_MODE" = script ] && printf true || printf false)" \
        "$([ "$RESTART_MODE" = lifecycle ] && printf true || printf false)" "$editor_language"
    exit 0
fi

if [ "$ACTION" = "status" ]; then
    load_settings
    if [ "$RESTART_MODE" != 'lifecycle' ]; then
        printf 'Content-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\n\r\n'
        printf '{"ok":true,"running":false,"state":"unsupported","code":4}\n'
        exit 0
    fi

    setup_lifecycle_env
    lifecycle_script="${package_root}/scripts/start-stop-status"
    [ -x "$lifecycle_script" ] ||
        json_error '500 Internal Server Error' 'Unable to execute start-stop-status'

    service_output=$("$lifecycle_script" status 2>&1)
    service_code=$?
    # Some legacy package scripts print "is not running" but incorrectly
    # return 0. Normalize that known case without changing signed scripts.
    if [ "$service_code" -eq 0 ]; then
        case "$service_output" in
            *' is not running'*) service_code=3 ;;
        esac
    fi
    case "$service_code" in
        0) service_state='running' ;;
        1) service_state='deadPid' ;;
        2) service_state='deadLock' ;;
        3) service_state='stopped' ;;
        150) service_state='broken' ;;
        *) service_state='unknown' ;;
    esac
    printf 'Content-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\n\r\n'
    printf '{"ok":true,"running":%s,"state":"%s","code":%s}\n' \
        "$([ "$service_code" -eq 0 ] && printf true || printf false)" \
        "$service_state" "$service_code"
    exit 0
fi

if [ "$ACTION" = "save" ]; then
    validate_save_request
    load_settings
    [ -f "$CONFIG_FILE" ] || json_error '404 Not Found' '配置文件不存在'
    [ -w "$CONFIG_FILE" ] || json_error '403 Forbidden' '没有写入配置文件的权限'
    case "${CONTENT_LENGTH:-}" in
        ''|*[!0-9]*) json_error '400 Bad Request' '无效的内容长度' ;;
    esac
    [ "$CONTENT_LENGTH" -le "$MAX_BYTES" ] || json_error '413 Payload Too Large' '内容超过 2 MiB 限制'

    config_dir=$(dirname -- "$CONFIG_FILE")
    config_name=$(basename -- "$CONFIG_FILE")
    # mkdir is atomic and acts as a portable BusyBox-compatible save lock.
    lock_dir="${config_dir}/.${config_name}.editor.lock"
    mkdir -- "$lock_dir" 2>/dev/null ||
        json_error '409 Conflict' '另一个保存操作正在进行，请稍后重试'
    tmp_file=''
    trap 'rm -f -- "$tmp_file"; rmdir -- "$lock_dir" 2>/dev/null' EXIT HUP INT TERM
    tmp_file=$(mktemp "${config_dir}/.${config_name}.tmp.XXXXXX") ||
        json_error '500 Internal Server Error' '无法在配置目录创建临时文件'

    if [ "$CONTENT_LENGTH" -eq 0 ]; then
        : > "$tmp_file"
    else
        dd bs="$CONTENT_LENGTH" count=1 of="$tmp_file" 2>/dev/null
    fi
    actual_size=$(wc -c < "$tmp_file" | tr -d ' ')
    [ "$actual_size" -eq "$CONTENT_LENGTH" ] || json_error '400 Bad Request' '未完整收到保存内容'

    # Keep three recoverable generations. .bak.1 is newest; backup failures
    # must stop the save before the active configuration is replaced.
    [ ! -e "${CONFIG_FILE}.bak.2" ] ||
        mv -f -- "${CONFIG_FILE}.bak.2" "${CONFIG_FILE}.bak.3" ||
        json_error '500 Internal Server Error' '无法轮换 .bak.3 备份'
    [ ! -e "${CONFIG_FILE}.bak.1" ] ||
        mv -f -- "${CONFIG_FILE}.bak.1" "${CONFIG_FILE}.bak.2" ||
        json_error '500 Internal Server Error' '无法轮换 .bak.2 备份'
    cp -p -- "$CONFIG_FILE" "${CONFIG_FILE}.bak.1" ||
        json_error '500 Internal Server Error' '无法创建 .bak.1 备份'
    mode=$(stat -c '%a' "$CONFIG_FILE" 2>/dev/null)
    owner=$(stat -c '%u:%g' "$CONFIG_FILE" 2>/dev/null)
    [ -n "$mode" ] || json_error '500 Internal Server Error' '无法读取配置文件权限'
    [ -n "$owner" ] || json_error '500 Internal Server Error' '无法读取配置文件所有者'
    chmod "$mode" "$tmp_file" ||
        json_error '500 Internal Server Error' '无法保留配置文件权限'
    tmp_owner=$(stat -c '%u:%g' "$tmp_file" 2>/dev/null)
    if [ "$tmp_owner" != "$owner" ]; then
        chown "$owner" "$tmp_file" ||
            json_error '500 Internal Server Error' '无法保留配置文件所有者'
    fi
    mv -- "$tmp_file" "$CONFIG_FILE" ||
        json_error '500 Internal Server Error' '替换配置文件失败'

    restart_state='配置保存成功'
    restart_code='saved'
    restart_ok=true
    if [ "$RESTART_MODE" = 'lifecycle' ]; then
        setup_lifecycle_env
        lifecycle_script="${package_root}/scripts/start-stop-status"
        if [ ! -f "$lifecycle_script" ]; then
            restart_state='配置已保存，但找不到 start-stop-status'
            restart_code='lifecycleMissing'
            restart_ok=false
        elif [ ! -x "$lifecycle_script" ]; then
            restart_state='配置已保存，但 start-stop-status 没有执行权限'
            restart_code='lifecycleNotExecutable'
            restart_ok=false
        else
            export SYNOPKG_PKG_STATUS=STOP
            if ! "$lifecycle_script" stop >/dev/null 2>&1; then
                restart_state='配置已保存，但套件停止失败'
                restart_code='stopFailed'
                restart_ok=false
            else
                export SYNOPKG_PKG_STATUS=START
                if "$lifecycle_script" start >/dev/null 2>&1; then
                    restart_state='配置已保存，套件已重新启动'
                    restart_code='restarted'
                else
                    restart_state='配置已保存，但套件启动失败'
                    restart_code='startFailed'
                    restart_ok=false
                fi
            fi
        fi
    elif [ "$RESTART_MODE" = 'script' ]; then
        case "$RESTART_SCRIPT" in
            /*) restart_path_ok=true ;;
            *) restart_path_ok=false ;;
        esac
        if [ "$restart_path_ok" != true ]; then
            restart_state='配置已保存，但 RESTART_SCRIPT 不是绝对路径'
            restart_code='scriptPathInvalid'
            restart_ok=false
        elif [ ! -f "$RESTART_SCRIPT" ]; then
            restart_state='配置已保存，但重启脚本不存在'
            restart_code='scriptMissing'
            restart_ok=false
        elif [ ! -x "$RESTART_SCRIPT" ]; then
            restart_state='配置已保存，但重启脚本没有执行权限'
            restart_code='scriptNotExecutable'
            restart_ok=false
        elif "$RESTART_SCRIPT" $RESTART_ARGS >/dev/null 2>&1; then
            restart_state='配置已保存，重启脚本执行成功'
            restart_code='scriptSucceeded'
        else
            restart_state='配置已保存，但重启脚本执行失败'
            restart_code='scriptFailed'
            restart_ok=false
        fi
    fi
    rmdir -- "$lock_dir" 2>/dev/null
    trap - EXIT HUP INT TERM
    printf 'Content-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\n\r\n'
    printf '{"ok":true,"message":"%s，最新备份为 .bak.1","messageCode":"%s","restartOk":%s,"bytes":%s}\n' \
        "$restart_state" "$restart_code" "$restart_ok" "$actual_size"
    exit 0
fi

cat <<'HTML'
Content-Type: text/html; charset=utf-8
Cache-Control: no-store
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'

<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Configuration Editor</title>
  <style>
    :root{--bg:#f4f7fb;--panel:#fff;--line:#dbe3ee;--text:#243247;--muted:#708198;--accent:#168c6a;--accent2:#2878d0;--danger:#d83b53}
    *{box-sizing:border-box}[hidden]{display:none!important}html,body{height:100%;margin:0}body{font:14px/1.5 system-ui,-apple-system,"Segoe UI","PingFang SC",sans-serif;color:var(--text);background:var(--bg)}
    .app{width:min(1240px,100%);height:100%;margin:auto;padding:16px;display:grid;grid-template-rows:auto auto minmax(260px,1fr) auto;gap:10px}
    header,.toolbar,.status,.editor{border:1px solid var(--line);background:var(--panel);box-shadow:0 5px 18px #31517610}
    header{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;border-radius:10px}
    h1{font-size:16px;margin:0;display:flex;align-items:center}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent);margin-right:9px}
    .head-meta{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:12px}.badge{padding:2px 8px;border-radius:999px;background:#eef4fb;color:#477091;font-weight:700;letter-spacing:.04em}
    .toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 10px;border-radius:10px;background:#fbfcfe}
    .service-tools{display:flex;gap:9px;align-items:center}
    button,input{height:35px;border:1px solid var(--line);border-radius:7px;color:var(--text);background:#fff;font:inherit}
    button{padding:0 14px;cursor:pointer;font-weight:600;transition:.15s}button:hover{border-color:#91a7c1;background:#f7f9fc}button:disabled{opacity:.5;cursor:wait}
    .primary{color:#fff;background:var(--accent);border-color:var(--accent)}.primary:hover{color:#fff;background:#11795b}.open{color:#fff;background:var(--accent2);border-color:var(--accent2)}.open:hover{color:#fff;background:#2168b3}
    input{width:100px;padding:0 10px;outline:none}input:focus{border-color:var(--accent2);box-shadow:0 0 0 3px #2878d018}.spacer{flex:1}.hint{color:var(--muted);font-size:12px}
    input[readonly]{background:#f5f7fa;color:#52657b;cursor:default}
    .editor{min-height:260px;display:grid;grid-template-columns:auto 1fr;border-radius:10px;overflow:hidden}
    #lines,#text,#highlight{margin:0;font:13px/1.65 ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;tab-size:4}
    #lines{min-width:56px;padding:16px 12px 16px 8px;text-align:right;color:#9aa9ba;background:#f6f8fb;border-right:1px solid var(--line);overflow:hidden;white-space:pre;user-select:none}
    .code-pane{position:relative;min-width:0;overflow:hidden;background:#fff}
    #highlight,#text{position:absolute;inset:0;width:100%;height:100%;padding:16px 18px;border:0;white-space:pre;overflow:auto}
    #highlight{pointer-events:none;color:#34445a;background:#fff}
    #text{resize:none;outline:0;color:transparent;background:transparent;caret-color:#172033;-webkit-text-fill-color:transparent}
    #text{scrollbar-color:#c4cfdd #f4f7fb;scrollbar-width:auto}
    #text::-webkit-scrollbar{width:12px;height:12px}#text::-webkit-scrollbar-track{background:#f4f7fb}#text::-webkit-scrollbar-thumb{background:#c4cfdd;border:3px solid #f4f7fb;border-radius:8px}#text::-webkit-scrollbar-thumb:hover{background:#9fadc0}#text::-webkit-scrollbar-corner{background:#f4f7fb}
    #text::selection{background:#b9d8ff88}
    .tok-key{color:#7c3aed;font-weight:600}.tok-string{color:#087f5b}.tok-number{color:#d9480f}.tok-bool{color:#1769aa;font-weight:600}.tok-null{color:#a33a91;font-weight:600}.tok-section{color:#b4236c;font-weight:700}.tok-comment{color:#8996a8;font-style:italic}.tok-punct{color:#63758a}.tok-var{color:#b45f06}.tok-keyword{color:#075fb8;font-weight:600}.tok-anchor{color:#9c36b5}
    .status{min-height:38px;display:flex;align-items:center;justify-content:space-between;padding:7px 12px;border-radius:9px;color:var(--muted)}
    .service-state{height:26px;padding:0 9px;border-radius:999px;font-size:12px}.service-state.running{color:#087f5b;background:#e7f8f1;border-color:#a8e3cf}.service-state.stopped{color:#b42318;background:#fff1f0;border-color:#ffc8c2}.service-state.unknown{color:#8a5b00;background:#fff8df;border-color:#f0d88a}
    #message.ok{color:var(--accent)}#message.error{color:var(--danger)}.dirty{color:#fbbf24!important}
    @media(max-width:650px){.app{padding:7px}.hint{display:none}.head-meta{gap:5px}.toolbar{gap:7px}.spacer{display:none}.toolbar input{flex:1}button{padding:0 11px}}
  </style>
</head>
<body>
<main class="app">
  <header>
    <h1><span class="dot"></span><span data-i18n="title">Configuration Editor</span></h1>
    <div class="head-meta"><button class="service-state unknown" id="serviceStatus" data-i18n-title="statusRefresh">Checking…</button><span class="badge" id="formatBadge">CONFIG</span><span id="stats">Preparing…</span></div>
  </header>
  <section class="toolbar">
    <button class="primary" id="save">✓ Save</button>
    <button id="reload">↻ Reload</button>
    <span class="spacer"></span>
    <span class="service-tools" id="serviceTools" hidden>
      <label class="hint" for="port" data-i18n="servicePort">Service port</label>
      <input id="port" type="text" readonly aria-readonly="true">
      <button class="open" id="open">↗ <span data-i18n="openService">Open service</span></button>
    </span>
  </section>
  <section class="editor">
    <pre id="lines" aria-hidden="true">1</pre>
    <div class="code-pane">
      <pre id="highlight" aria-hidden="true"></pre>
      <textarea id="text" wrap="off" spellcheck="false" aria-label="Configuration file"></textarea>
    </div>
  </section>
  <footer class="status"><span id="message">Loading configuration…</span><span id="cursor">Line 1, Column 1</span></footer>
</main>
<script>
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const text = $('text'), lines = $('lines'), highlight = $('highlight'), message = $('message'), save = $('save');
  let baseline = '', busy = false, language = 'generic', openPath = '/', messages = {};
  const englishFallback = {
    title:'Configuration Editor',servicePort:'Service port',openService:'Open service',
    save:'✓ Save',saveChanges:'● Save changes',reload:'↻ Reload',
    preparing:'Preparing…',loading:'Loading configuration…',loaded:'Latest content loaded',
    unsavedReload:'There are unsaved changes. Reload anyway?',saving:'Saving and creating backup…',
    invalidPort:'The configured port is invalid',lineColumn:'Line {line}, Column {column}',
    stats:'{lines} lines · {bytes} bytes',configAria:'Configuration file',
    saved:'Configuration saved; backup created',restarted:'Configuration saved; package restarted',
    lifecycleMissing:'Configuration saved, but start-stop-status was not found',
    lifecycleNotExecutable:'Configuration saved, but start-stop-status is not executable',
    stopFailed:'Configuration saved, but the package could not be stopped',
    startFailed:'Configuration saved, but the package could not be started',
    scriptPathInvalid:'Configuration saved, but the script path is invalid',
    scriptMissing:'Configuration saved, but the restart script was not found',
    scriptNotExecutable:'Configuration saved, but the restart script is not executable',
    scriptSucceeded:'Configuration saved; restart script completed',
    scriptFailed:'Configuration saved, but the restart script failed',
    statusChecking:'Checking…',statusRefresh:'Click to check again',statusRunning:'Running',
    statusStopped:'Stopped',statusDeadPid:'Process failed',statusDeadLock:'Lock error',
    statusBroken:'Package broken',statusUnknown:'Status unknown',
    savedNotRunning:'Configuration saved, but the service is not running'
  };
  const t = (key, vars={}) => {
    let value=messages[key]||englishFallback[key]||key;
    Object.keys(vars).forEach(name=>{value=value.split(`{${name}}`).join(String(vars[name]))});
    return value;
  };
  function localeCode() {
    const requested=new URLSearchParams(location.search).get('lang')||'';
    if(/^[a-z]{3}$/i.test(requested)) return requested.toLowerCase();
    return 'enu';
  }
  async function loadMessages() {
    const locale=localeCode();
    const loadJson=code=>fetch(`i18n/${code}.json`,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json()});
    messages=await loadJson(locale).catch(()=>loadJson('enu')).catch(()=>englishFallback);
    document.documentElement.lang=messages._htmlLang||'en';
    document.title=t('title');
    document.querySelectorAll('[data-i18n]').forEach(node=>node.textContent=t(node.dataset.i18n));
    document.querySelectorAll('[data-i18n-title]').forEach(node=>node.title=t(node.dataset.i18nTitle));
    text.setAttribute('aria-label',t('configAria'));
    $('reload').textContent=t('reload'); refresh(); cursor();
  }
  const endpoint = action => {
    const params=new URLSearchParams(location.search);
    params.set('action',action);
    return `${location.pathname}?${params}`;
  };
  const setMessage = (value, type='') => { message.textContent=value; message.className=type; };
  const esc = value => value.replace(/[&<>]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
  function colorValue(value) {
    const token=/(["'])(?:\\.|(?!\1)[^\\])*\1|\b(?:true|false)\b|\bnull\b|[-+]?\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?)\b/g;
    let html='', last=0, match;
    while((match=token.exec(value))) {
      html+=esc(value.slice(last,match.index));
      const raw=match[0], cls=/^["']/.test(raw)?'tok-string':/^(true|false)$/.test(raw)?'tok-bool':raw==='null'?'tok-null':'tok-number';
      html+=`<span class="${cls}">${esc(raw)}</span>`; last=match.index+raw.length;
    }
    return html+esc(value.slice(last));
  }
  function splitComment(line, markers='#') {
    let quote='', slash=false, comment=-1;
    for(let i=0;i<line.length;i++) {
      const ch=line[i];
      if(slash){slash=false;continue}
      if(ch==='\\'&&quote){slash=true;continue}
      if((ch==='"'||ch==="'")){quote=quote===ch?'':quote||ch;continue}
      if(markers.includes(ch)&&!quote){comment=i;break}
    }
    return [comment<0?line:line.slice(0,comment),comment<0?'':line.slice(comment)];
  }
  const withComment=(html,note)=>html+(note?`<span class="tok-comment">${esc(note)}</span>`:'');
  function colorToml(line) {
    const [code,note]=splitComment(line);
    let html;
    if(/^\s*\[\[?.*\]\]?\s*$/.test(code)) html=`<span class="tok-section">${esc(code)}</span>`;
    else {
      const eq=code.indexOf('=');
      html=eq>=0
        ? `<span class="tok-key">${esc(code.slice(0,eq).trimEnd())}</span><span class="tok-punct">${esc(code.slice(code.slice(0,eq).trimEnd().length,eq+1))}</span>${colorValue(code.slice(eq+1))}`
        : colorValue(code);
    }
    return withComment(html,note);
  }
  function colorYaml(line) {
    const [code,note]=splitComment(line), match=code.match(/^(\s*-\s+|\s*)([^:]+)(:\s*)(.*)$/);
    if(match) return withComment(`${esc(match[1])}<span class="tok-key">${esc(match[2])}</span><span class="tok-punct">${esc(match[3])}</span>${colorValue(match[4])}`,note);
    return withComment(colorValue(code),note);
  }
  function colorJson(line) {
    const pair=line.match(/^(\s*)("(?:\\.|[^"\\])*")(\s*:)(.*)$/);
    if(pair) return `${esc(pair[1])}<span class="tok-key">${esc(pair[2])}</span><span class="tok-punct">${esc(pair[3])}</span>${colorValue(pair[4])}`;
    return colorValue(line).replace(/([{}\[\],:])/g,'<span class="tok-punct">$1</span>');
  }
  function colorIni(line) {
    const [code,note]=splitComment(line,'#;');
    if(/^\s*\[.*\]\s*$/.test(code)) return withComment(`<span class="tok-section">${esc(code)}</span>`,note);
    const match=code.match(/^(\s*)([^=:]+)(\s*[=:]\s*)(.*)$/);
    return withComment(match?`${esc(match[1])}<span class="tok-key">${esc(match[2].trimEnd())}</span><span class="tok-punct">${esc(match[3])}</span>${colorValue(match[4])}`:colorValue(code),note);
  }
  function colorEnv(line) {
    const [code,note]=splitComment(line), match=code.match(/^(\s*(?:export\s+)?)([A-Za-z_][\w]*)(\s*=\s*)(.*)$/);
    return withComment(match?`${esc(match[1])}<span class="tok-key">${esc(match[2])}</span><span class="tok-punct">${esc(match[3])}</span>${colorShellValue(match[4])}`:colorShellValue(code),note);
  }
  function colorShellValue(value) {
    return colorValue(value).replace(/(\$\{?[A-Za-z_][\w]*\}?)/g,'<span class="tok-var">$1</span>');
  }
  function colorShell(line) {
    const [code,note]=splitComment(line);
    let html=colorShellValue(code);
    html=html.replace(/\b(if|then|else|elif|fi|for|while|do|done|case|esac|function|in)\b/g,'<span class="tok-keyword">$1</span>');
    return withComment(html,note);
  }
  function colorLine(line) {
    if(language==='toml') return colorToml(line);
    if(language==='yaml') return colorYaml(line);
    if(language==='json') return colorJson(line);
    if(language==='ini') return colorIni(line);
    if(language==='env') return colorEnv(line);
    if(language==='shell') return colorShell(line);
    return colorIni(line);
  }
  function paint() {
    highlight.innerHTML=text.value.split('\n').map(colorLine).join('\n')+(text.value.endsWith('\n')?' ':'');
    highlight.scrollTop=text.scrollTop; highlight.scrollLeft=text.scrollLeft;
  }
  function refresh() {
    const count = text.value.split('\n').length;
    lines.textContent = Array.from({length:count},(_,i)=>i+1).join('\n');
    $('stats').textContent = t('stats',{lines:count,bytes:new Blob([text.value]).size});
    const dirty = text.value !== baseline;
    save.textContent = dirty ? t('saveChanges') : t('save');
    message.classList.toggle('dirty', dirty && !message.classList.contains('error'));
    paint();
  }
  function cursor() {
    const before=text.value.slice(0,text.selectionStart), row=before.split('\n');
    $('cursor').textContent=t('lineColumn',{line:row.length,column:row[row.length-1].length+1});
  }
  async function refreshMeta() {
    const meta=await fetch(endpoint('meta'),{cache:'no-store'}).then(x=>x.json()).catch(()=>null);
    language=meta?.language||'generic';
    openPath=meta?.openPath||'/';
    $('formatBadge').textContent=language==='generic'?'CONFIG':language.toUpperCase();
    const hasPort=Boolean(meta?.defaultPort);
    $('serviceTools').hidden=!hasPort;
    port.value=hasPort?meta.defaultPort:'';
    $('serviceStatus').hidden=meta?.statusEnabled===false;
    return meta;
  }
  async function refreshServiceStatus(attempts=1) {
    const badge=$('serviceStatus');
    if(badge.hidden) return null;
    badge.textContent=t('statusChecking');
    badge.className='service-state unknown';
    let data=null;
    for(let attempt=0;attempt<attempts;attempt++) {
      try {
        data=await fetch(endpoint('status'),{cache:'no-store'}).then(x=>x.json());
        if(!data.ok) throw new Error(data.message||t('statusUnknown'));
      } catch (_) {
        data=null;
      }
      if(data?.running || attempt===attempts-1) break;
      await new Promise(resolve=>setTimeout(resolve,600));
    }
    const labels={running:'statusRunning',stopped:'statusStopped',deadPid:'statusDeadPid',deadLock:'statusDeadLock',broken:'statusBroken',unknown:'statusUnknown'};
    badge.textContent=data?t(labels[data.state]||'statusUnknown'):t('statusUnknown');
    badge.className=`service-state ${data?.running?'running':data?.state==='unknown'||!data?'unknown':'stopped'}`;
    return data;
  }
  async function load() {
    if (text.value !== baseline && !confirm(t('unsavedReload'))) return;
    setBusy(true); setMessage(t('loading'));
    try {
      const r=await fetch(endpoint('load'),{cache:'no-store'});
      const contentType=r.headers.get('content-type')||'';
      if(contentType.includes('application/json')) {
        const data=await r.json();
        if(data.ok===false) throw new Error(data.message || `读取失败 (${data.status||r.status})`);
      }
      if(!r.ok) {
        const raw=await r.text();
        let detail='';
        try { detail=JSON.parse(raw).message||'' } catch (_) { detail=raw.replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,180) }
        throw new Error(detail || `读取失败 (${r.status})`);
      }
      baseline=text.value=await r.text();
      await refreshMeta();
      await refreshServiceStatus();
      refresh(); cursor(); setMessage(t('loaded'),'ok');
    } catch(e) { setMessage(e.message,'error'); } finally { setBusy(false); }
  }
  async function persist() {
    setBusy(true); setMessage(t('saving'));
    try {
      const r=await fetch(endpoint('save'),{method:'POST',headers:{'Content-Type':'text/plain;charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body:text.value});
      const data=await r.json().catch(()=>({message:`保存失败 (${r.status})`}));
      if(!r.ok || !data.ok) throw new Error(data.message);
      baseline=text.value; await refreshMeta(); refresh();
      const service=await refreshServiceStatus(5);
      if(data.restartOk!==false && service && !service.running) {
        setMessage(t('savedNotRunning'),'error');
      } else {
        setMessage(data.messageCode?t(data.messageCode):data.message,data.restartOk===false?'error':'ok');
      }
    } catch(e) { setMessage(e.message,'error'); } finally { setBusy(false); }
  }
  function setBusy(value){busy=value; $('reload').disabled=value; save.disabled=value}
  text.addEventListener('input',()=>{refresh();cursor()});
  text.addEventListener('scroll',()=>{lines.scrollTop=text.scrollTop;highlight.scrollTop=text.scrollTop;highlight.scrollLeft=text.scrollLeft});
  text.addEventListener('click',cursor); text.addEventListener('keyup',cursor);
  text.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();if(!busy)persist()}
    if(e.key==='Tab'){e.preventDefault();const a=text.selectionStart,b=text.selectionEnd;text.setRangeText('    ',a,b,'end');refresh()}
  });
  $('reload').addEventListener('click',load); save.addEventListener('click',persist);
  $('serviceStatus').addEventListener('click',()=>refreshServiceStatus());
  const port=$('port');
  $('open').addEventListener('click',()=>{
    const p=Number(port.value);
    if(!Number.isInteger(p)||p<1||p>65535){setMessage(t('invalidPort'),'error');return}
    const host=location.hostname.includes(':')?`[${location.hostname}]`:location.hostname;
    window.open(`${location.protocol}//${host}:${p}${openPath}`,'_blank','noopener,noreferrer');
  });
  window.addEventListener('beforeunload',e=>{if(text.value!==baseline){e.preventDefault();e.returnValue=''}});
  loadMessages().finally(load);
})();
</script>
</body>
</html>
HTML
