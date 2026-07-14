# computer-use-fallback-mac

独立的 macOS Computer Use MCP 组件。它以“应用 + 窗口”为操作边界，通过 Accessibility 语义控制后台窗口，不依赖当前桌面最前端命中，也不移动或抢占实体鼠标。

> 当前仓库为私有预发布组件。对外公开或再分发前，需要完成独立的来源与许可证审查；详见 [NOTICE](NOTICE) 和 [LICENSE](LICENSE)。

## 核心能力

- `get_app_state`：以 ScreenCaptureKit 为首选、CoreGraphics 为后备，抓取指定应用窗口；遮挡该窗口的其他应用不会进入截图。
- `click`、`drag`、`scroll`：优先使用 `AXPress`、滚动按钮和控件值语义；坐标始终是目标窗口截图的局部坐标。
- `set_value`、`type_text`、`select_text`、`press_key`：只作用于显式目标的 Accessibility 元素；无法验证的后台投递会报错。
- `list_apps`、`list_windows`：发现可寻址应用、窗口 ID 和窗口边界。
- 每个 MCP 进程拥有独立的持久 Python worker、状态快照、虚拟光标和 overlay；同一窗口用跨进程锁串行化，不同窗口可并行。
- 成功的点击、滚动、拖动和 down/up 会把真实动作点写入当前 session；点击穿透 live overlay 与下一次 `get_app_state` PNG 使用同一坐标和反馈阶段。
- 虚拟光标样式 `fallback-official-aqua-arrow-v2` 使用 13×18 逻辑像素的半透明冷白箭头、柔和光晕和低透明浅青尾部内缘；无圆点、无硬环，也不包含任何官方位图或矢量资产。
- 兼容旧工具名，但旧鼠标动作必须提供 `app`/`windowId`，或先调用 `get_app_state` 绑定目标。

## 安全模型

生产动作路径禁止全局 `CGEventPost`、`CGEventPostToPid`、`pyautogui` 鼠标动作、AppleScript 激活、`AXRaise` 和焦点抢占。内置 runtime 不会“先投递事件、再报告无法验证”；应用若没有可验证的 AX 后台机制，组件直接返回 `unsupported_background_action`。

这不是对所有 macOS 应用的无条件承诺。准确边界是：目标控件必须暴露可用的 Accessibility 语义，或目标应用必须能够确认进程定向事件。非 AX 画布等无法验证的控件会明确失败。

## 使用顺序

1. 调用 `list_apps`，必要时用 `list_windows` 取得窗口 ID。
2. 调用 `get_app_state({app, windowId})`，读取窗口截图、元素索引和局部边界。
3. 优先按 `element_index` 操作；坐标操作使用该次窗口截图的坐标。
4. 窗口内容变化后重新调用 `get_app_state`。过期索引会返回 `stale_state`。

动作后的文本块包含 `cursorFeedback`：`drawn` 表示本次窗口截图是否合成光标，`imagePoint` 是截图像素坐标，`phase` 描述按下/释放/稳定阶段。分步 `mouse_down` 会明确返回 `delivery: pending`，只有匹配的同 session `mouse_up` 才完成该手势；首次状态或目标进程/窗口不匹配时不会绘制。

## 安装与启动

完整安装方法见 [MCP_INSTALL.md](MCP_INSTALL.md)。本地启动：

```bash
npm install
npm start
```

首次运行会在项目内创建 `.venv` 并安装 `runtime/requirements.txt`。

## 验证

```bash
npm run test:unit
npm run test:integration
npm run test:live
npm run test:all
```

默认 `npm test` 只运行非侵入式 CI 门禁；真实 GUI matrix 必须显式运行 `npm run test:live`。

已验证的 live matrix：

- Calculator：以 `open -n` 创建并验证独立进程，窗口被覆盖时执行后台按钮点击；已有 Calculator 进程不变。
- TextEdit：独立临时实例被覆盖时设置文本值；不接触用户文档。
- Safari：以 `open -n -F` 创建不恢复历史会话的独立实例，验证并只清理该实例，访问本机临时页面，被覆盖时执行网页按钮操作。
- Microsoft Edge：仅在 Edge 已运行时，live gate 对一个现有后台窗口新增并关闭右侧新标签，核对原标签标题与数量完全恢复；不会启动/激活 Edge、创建窗口、导航地址或结束用户进程。Edge 未运行时该项跳过。
- 双 worker：同时控制两个被覆盖的 AppKit 目标，点击、文本、拖动、滚动、光标状态均无串扰。
- 官方对照：Calculator 的初始态、点击态、稳态、均匀背景和移位状态均已采样；fallback 使用独立绘制的近白半透明箭头与柔和光晕，并以浅青尾部内缘和非对称切角作细微区分。
- Overlay 激活隔离：独立 session overlay 使用 nonactivating `NSPanel` 和 `NSApplicationActivationPolicyProhibited`；测试按精确 PID 验证它不会成为前台应用。
- 完整焦点生命周期：live/integration gate 在启动任何目标或遮挡层之前开始监听 `NSWorkspaceDidActivateApplicationNotification`。受保护目标、遮挡层或 overlay 只要曾短暂成为前台即失败；普通键盘输入不能把焦点变化解释为用户操作，只有实体鼠标按下或 Command-Tab 可归因第三方应用切换。
- 测试遮挡层：`CU Blocker Harness` 是用于证明后台动作不会落到前台桌面的测试窗口，并发用例会创建两个。它不是虚拟鼠标或产品 UI；默认仅 2% 不透明度，使用不可激活面板并由测试自动清理。设置 `CU_BLOCKER_VISIBLE=1` 才显示红色诊断外观。

`npm run test:live` 会创建并清理一次性应用窗口，需本机已授予 Accessibility 和 Screen Recording 权限。权限说明见 [PERMISSIONS.md](PERMISSIONS.md)。

## 主要入口

- `start-mcp.mjs`：stdio MCP 入口。
- `src/mcp-server.mjs`：MCP server。
- `src/runtime-worker.mjs`：Node 侧持久 worker 客户端。
- `runtime/worker.py`：Python JSONL worker。
- `runtime/cu_runtime/`：目标解析、窗口截图、AX 状态、动作路由、会话隔离。
- `docs/COMPUTER_USE_OPERATION_GUIDE.md`：调用和错误恢复指南。

## 仓库结构

```text
src/                 Node.js MCP 服务与协议映射
runtime/             Python/macOS 原生运行时
tests/               单元、集成、live 与安装验证
scripts/             可重复的维护和可视化脚本
docs/                用户操作文档
knowledge/           已核验的架构、质量与任务证据
.github/              CI 与依赖更新配置
```

本地 agent 会话、交接记录、运行时状态、依赖目录、凭据和个人绝对路径不属于仓库发布资产，并由测试与 `.gitignore` 双重阻止。

## 贡献与安全

- 贡献流程和必跑门禁见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，不要在普通 issue 中披露。
- 版本变化见 [CHANGELOG.md](CHANGELOG.md)。
- 行为规范见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

Hosted CI 只运行确定性测试、干净安装和依赖审计。需要真实 Accessibility/Screen Recording 权限以及实体鼠标与前台应用观测的 live matrix 必须在受控 Mac 上执行。

## 来源说明

本组件最初从 `NanmiCoder/cc-haha` 的 Computer Use runtime 中提取，之后重构为独立的应用/窗口定向 MCP，并新增了严格后台动作、会话隔离、虚拟光标和验证体系。原有 MIT 归属保留在 [LICENSE](LICENSE)，修改范围与发布限制见 [NOTICE](NOTICE)。
