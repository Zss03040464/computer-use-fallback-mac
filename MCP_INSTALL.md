# MCP Install Guide

本项目是一个独立的 macOS MCP stdio server，可接入兼容 MCP stdio 配置的 Agent 平台。

## Requirements

- macOS 14 或更高版本。
- Node.js 20 或更高版本。
- Python 3.9 或更高版本。
- 启动 MCP 的宿主应用已获得 Accessibility 和 Screen Recording 权限。
- Calculator、TextEdit、Safari 为 live matrix 所需系统应用；Edge matrix 需要安装 Microsoft Edge。

## Install

```bash
git clone <repository-url> computer-use-fallback-mac
cd computer-use-fallback-mac
npm install
npm run test:unit
```

首次启动时，`src/bridge.mjs` 会在仓库内创建 `.venv`，并按 `runtime/requirements.txt` 安装 PyObjC、Pillow 等依赖。`.venv`、会话状态、PID、lock 和日志不属于发布资产。

## Generic MCP stdio configuration

把路径换成实际仓库绝对路径：

```json
{
  "mcpServers": {
    "computer-use-fallback-mac": {
      "command": "node",
      "args": ["/absolute/path/to/computer-use-fallback-mac/start-mcp.mjs"]
    }
  }
}
```

不需要设置 `cwd`；服务从 `import.meta.url` 计算项目根目录。

## Verify the tool surface

在宿主平台加入上述 stdio entry，重新加载后确认 `tools/list` 至少包含：

- `list_apps`
- `list_windows`
- `get_app_state`
- `click`
- `drag`
- `scroll`
- `press_key`
- `type_text`
- `set_value`
- `select_text`
- `perform_secondary_action`
- `virtual_cursor_overlay`

## Verify The Installation

```bash
npm run test:unit
npm run test:integration
npm run test:live
npm run test:clean-install
npm run test:virtual-static
npm run test:overlay-style
npm run test:live-cursor-overlay
npm run test:installability
```

完整门禁：

```bash
npm run test:all
```

`test:integration` 和 `test:live` 已强制串行，避免 GUI fixture 相互遮挡。live matrix 使用临时窗口、临时文档、本机 HTTP 页面和带唯一 token 的 Edge 临时 profile；不会复用用户浏览器标签或文档。

`npm test` 不启动真实 GUI 应用。只有显式的 `test:live` / `test:all` 会运行 live matrix。系统应用测试先记录启动前进程，再用 `open -n -F` 创建不恢复历史会话的独立实例，验证 executable 与新 PID 后才允许清理。

## Expected Behavior

- 先以 `get_app_state` 绑定目标应用/窗口，再使用元素索引或窗口局部坐标。
- 被其他应用覆盖的目标仍能接收其暴露的后台安全动作。
- 实体鼠标位置和最前端应用在动作前后保持不变。
- 不同 MCP 进程拥有不同 session、cursor、snapshot 和 overlay。
- 成功鼠标动作会自动启动当前 session 的点击穿透 overlay；下一次匹配窗口的 `get_app_state` PNG 也会显示同一动作点。
- overlay 启动异常会作为 `cursorFeedback.warning` 返回，不会把已经完成的动作伪装成失败并诱发重试。
- 分步 `mouse_down` 的反馈明确标记为 `cursorFeedback.delivery=pending`；同 session 的匹配 `mouse_up` 才完成手势。
- 不支持或无法验证的动作返回结构化错误，不会落到当前桌面最前端窗口。

## Troubleshooting

- `permission_missing` 或空白截图：检查 [PERMISSIONS.md](PERMISSIONS.md)，授权后重启 MCP 宿主应用。
- `stale_state`：重新调用 `get_app_state`，不要复用旧 element index。
- `target_busy`：另一会话正在控制同一窗口；稍后重试。
- `unverified_delivery`：该控件没有可确认的后台投递机制；不要改用全局点击兜底。
- 工具未出现：用 `node /absolute/path/start-mcp.mjs` 检查路径，再运行 `tests/node/mcp-transport.test.mjs`。
- overlay 残留：正常情况下 owner worker 退出后 overlay 会自动退出；也可调用 `virtual_cursor_overlay` 的 `stop`，清理只影响当前 MCP session。
