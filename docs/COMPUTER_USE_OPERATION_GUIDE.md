# Computer Use Operation Guide

## App-targeted control model

本组件采用应用状态优先模型：先取得指定应用窗口的截图与 Accessibility 元素，再按元素或窗口局部坐标执行动作。窗口被其他应用遮挡时，支持的动作仍直接作用于目标应用，实体鼠标和最前端应用不变。

## Virtual mouse

当前 fallback 已从桌面全局坐标模型切换为显式应用/窗口模型：

- `get_app_state` 只抓取目标窗口，并返回窗口局部坐标、元素索引和 generation。
- `click` 优先执行目标元素暴露的 `AXPress` 或 `AXShowMenu`。
- `drag` 对 slider、scrollbar 和 splitter 使用 AX value 语义。
- `scroll` 优先使用滚动区动作或滚动条方向按钮。
- 文本和值操作只写目标 AX 元素，并检查可观察值是否实际变化。
- 内置 runtime 不发送无法确认的 PID 事件；没有 AX 语义时在投递前直接报错。只有外部注入且能提供真实应用确认的 backend 才可扩展该边界。
- 已验证的鼠标动作会更新 session 光标、自动维持 live overlay，并在下一次匹配目标的 `get_app_state` PNG 中合成同一光标。释放阶段会短暂增强光晕，再衰减为稳定状态。

## Recommended Workflow

1. `list_apps` 确认应用标识。
2. 多窗口应用先调用 `list_windows({app})` 选择 `windowId`。
3. `get_app_state({app, windowId})` 获取新状态。
4. 优先按 `element_index` 操作。坐标点击使用响应截图中的局部坐标。
5. 每次页面加载、窗口移动、滚动或控件树改变后重新查询状态。
6. 可读取响应末尾的 `cursorFeedback.imagePoint` 核对动作位置；`drawn:false` 会给出 `no_feedback`、`target_mismatch` 或 `out_of_bounds` 原因。
7. 处理结构化错误：
   - `stale_state`：重新查询。
   - `target_busy`：稍后重试同一窗口。
   - `element_not_actionable`：选择元素实际暴露的 action。
   - `unverified_delivery` / `unsupported_background_action`：停止，不使用全局桌面点击绕过。

## Coordinate Pitfalls

- `get_app_state` 坐标原点在目标窗口截图左上角，不是桌面原点。
- 不要把旧的 display screenshot 坐标直接传给 app-targeted action。
- screenshot 像素尺寸可能和窗口逻辑尺寸不同；运行时会按 `scaleX` / `scaleY` 转换。
- 窗口移动或缩放后旧 capture 会失效，应重新查询。
- 多显示器的桌面坐标可为负；调用者仍应只传窗口局部坐标。

## Concurrency

每个 MCP server 进程对应一个 session 和一个持久 Python worker。不同目标可并行；同一 bundle/window 用跨进程 lock 串行化。一个 session 的 cursor、pressed button、snapshot 或 overlay 不会被另一个 session 读取或清理。

## Verification Boundaries

通过动作返回值不能替代目标状态验证。组件已经拒绝已知无法观察的投递，但调用方在关键操作后仍应重新调用 `get_app_state`。对于非 AX 画布、游戏渲染面或不公开后台语义的应用，明确错误是正确结果。
