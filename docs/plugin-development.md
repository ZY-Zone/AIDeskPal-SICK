# 插件开发文档 / Plugin Development

插件是运行在桌宠进程内的本地 Python 代码，可以添加托盘命令、注册动作、监听上下文、
说话或响应事件。它们**不是沙箱**：声明权限是给用户的知情与 API 层面的约束，信任边界
与普通 Python 程序相同。请只加载可信来源的插件。

插件 API 版本：`1`。

## 1. 目录结构

```
plugins/
  com.example.my_plugin/
    plugin.json
    plugin.py
    README.md
    assets/...
```

三个加载位置（后面的优先覆盖同 id 插件）：

1. `<安装目录>\plugins\`（随程序分发）
2. `<数据目录>\market\plugins\`（市场安装）
3. `<数据目录>\plugins\`（用户手动安装）

发行版默认数据目录是 exe 同级的 `user_data\`；源码运行通常是
`%LOCALAPPDATA%\AIDeskPal-SICK\`；实际路径见设置界面底部，可用
`AIDESKPAL_DATA_DIR` 覆盖。

插件默认不会自动启用。启用状态保存在设置文件的 `plugins.enabled` 列表。

## 2. plugin.json

```json
{
  "schema_version": 1,
  "id": "com.example.my_plugin",
  "name": "我的桌宠插件",
  "version": "1.0.0",
  "api_version": 1,
  "entry": "plugin.py",
  "description": "这个插件让桌宠在检测到专注时……",
  "author": "your-name",
  "homepage": "https://example.com",
  "permissions": [
    "context.read",
    "actions.play",
    "speech",
    "ui.tray",
    "events"
  ]
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 3–80 位字母/数字/`.`/`_`/`-`，建议反向域名 |
| `name` | 是 | 显示名称 |
| `version` | 是 | 语义化版本 |
| `api_version` | 是 | 当前只支持 `1` |
| `entry` | 是 | 插件目录内的相对 Python 文件 |
| `permissions` | 建议 | 见下表；未声明的 API 会抛 `PermissionError` |

### 权限

| 权限 | 允许的 API |
| --- | --- |
| `context.read` | `api.current_context()` |
| `actions.play` | `api.play_action()` |
| `actions.register` | `api.register_action()` |
| `speech` | `api.speak()` |
| `ui.tray` | `api.register_tray_action()` |
| `events` | `api.on()` / `api.emit()` |
| `settings.read` | `api.settings` |
| `settings.write` | `api.update_settings()` |
| `network` | 声明插件会访问网络（仅提示用户；Python 本身不受限） |


## 3. 生命周期

`plugin.py` 必须导出 `setup(api)`。返回值可以是带 `teardown()` 的对象，也可以是 `None`。

```python
def setup(api):
    api.log("hello")

    class Plugin:
        def teardown(self):
            api.log("bye")

    return Plugin()
```

- 加载：启动程序、保存设置后重新加载插件、启用插件时。
- 执行：`setup` 在 Qt 主线程中调用；不要在其中做长时间阻塞网络/文件操作。
- 卸载：停用插件、退出程序、重新加载插件时，先调用 `teardown()`，再自动注销该插件的事件和托盘命令。
- 加载错误会被捕获并显示在"设置 → 插件"中，不会阻止其他插件。

## 4. 最小示例

```python
def setup(api):
    last_note = {"at": 0.0}

    def say_hi():
        context = api.current_context()
        app = context.get("category", "other")
        api.speak(f"现在在 {app}，我陪你一会儿。")
        api.play_action("wave_hello")

    def on_tick(**payload):
        # 每 60 秒一次；不要在这里做重活
        if payload.get("context", {}).get("category") == "code":
            api.log("user is coding")

    api.register_tray_action("让桌宠打个招呼", say_hi)
    api.on("tick", on_tick)
```

完整可运行示例：`plugins/com.aideskpal.focus_orbit/`。

## 5. API 参考

### `api.id`
当前插件 id。

### `api.data_dir`
插件专属可写目录，自动创建：
`<数据目录>\plugin_data\<id>\`。

### `api.log(message)`
写入主日志。不要记录用户输入、窗口标题或密码。

### `api.speak(text, emotion="calm", style="soft")`
显示气泡。需要 `speech` 权限。`style`：`soft`、`star`、`warm`、`none`。
会尊重用户的"关闭说话"设置；被关闭时无动作。

### `api.play_action(action_id) -> bool`
播放当前模型的某个动作。需要 `actions.play`。动作 id 不存在或正在拖动时返回 `False`。
这不会改变 AI 的自动行为，但会立即覆盖当前播放动作；正常结束后回到待机。

### `api.register_tray_action(label, callback)`
在托盘"插件功能"子菜单中添加一项。需要 `ui.tray`。回调在 Qt 主线程执行；
可以多次调用。插件卸载时自动移除。

### `api.register_action(action) -> bool`
注册一个 JSON 动作（格式见 [action-authoring.md](action-authoring.md)），需要
`actions.register`。动作的 `model` 必须等于当前启用模型的动作包 ID，否则被拒绝。
注册成功后会持久化到插件动作注册表，重启后仍会加载。

### `api.current_context() -> dict`
需要 `context.read`。只返回经过隐私过滤的摘要：

```json
{
  "application": "Code.exe",
  "category": "code",
  "idle_seconds": 42,
  "typing_per_minute": 180,
  "current_action": "focus_company",
  "time": "23:41",
  "affinity": 28
}
```

`application` 在隐私窗口下为 `protected`，`category` 为 `private`。

### `api.on(event, callback)`
订阅事件，需要 `events`。回调参数根据事件变化，回调内部异常会被记录，不影响其他插件。
允许事件：

| 事件 | 参数 |
| --- | --- |
| `tick` | `context`、`snapshot`、`interval_seconds` |
| `action_started` | `action_id` |
| `action_finished` | `action_id` |
| `speech` | `text`、`emotion` |
| `interaction` | `trigger`、`x`、`y` |
| `foreground_changed` | `context` |
| `config_changed` | `config`（只读快照） |

### `api.emit(event, **payload)`
发布一个白名单事件。需要 `events`。通常不需要；这是给多个插件之间协作的轻量总线。

### `api.settings` / `api.update_settings(values)`
需要 `settings.read` / `settings.write`。每个插件一个 JSON 对象，保存在
`<数据目录>\plugin_data\<id>.json`，值必须是 JSON 可序列化类型。

## 6. 注册动作示例

```python
ACTION = {
    "schema_version": "1.0",
    "model": "citlali_summer",
    "id": "plugin_star_greeting",
    "name": "星礼",
    "description": "双手举起，向用户轻轻行礼。适合插件提醒被用户接受时使用。",
    "category": "greeting",
    "loop": False,
    "duration": 2.0,
    "ai_visible": True,
    "content": {
        "duration": 2.0,
        "bones": {
            "<模型里的骨骼名>": {
                "rotation": [
                    {"t": 0, "rot": [0, 0, 0]},
                    {"t": 0.7, "rot": [8, 0, 0]},
                    {"t": 2.0, "rot": [0, 0, 0]}
                ]
            }
        }
    }
}

def setup(api):
    api.register_action(ACTION)
```

注册的动作既可由插件 `play_action` 调用，也会进入 AI 动作目录（若 `ai_visible=true`）。
因此描述必须按 action-authoring.md 的规范写给 AI 看。

## 7. 打包到市场

1. 把插件目录内容打包成 ZIP，`plugin.json` 必须在 ZIP 根目录或唯一的一层目录中。
2. 登录创作者中心 `/cwwlc`，选择"上传插件"。
3. 服务器会检查 `plugin.json`、`entry` 是否存在、权限是否在白名单、ZIP 是否符合安全限制。
4. 管理员审核通过后，用户在桌面端「设置 → 市场 → 插件」中下载。
5. 市场 ZIP 不会被服务器执行；用户安装后在设置里手动启用。

不要把 `.venv`、`__pycache__`、本机绝对路径或密钥放进 ZIP。

## 8. 安全与限制

- 插件能访问 Python 能访问的一切；API 权限不是沙箱。
- 不要自动下载并执行远程代码。
- 不要在日志/气泡中回显窗口标题、按键内容或用户私密文本。
- 不要在 `setup` 中启动未受控线程而不在 `teardown` 停止。
- 不要修改宿主窗口的几何或按钮；使用提供的托盘/动作/气泡 API。
- 插件异常不应影响主程序；事件总线和加载器会捕获异常，但不保证能恢复被破坏的状态。
- 当前 UI 不提供插件自定义设置面板；可以用托盘命令 + `QInputDialog`? 不要依赖未暴露的 Qt 内部对象。
  推荐把可配置项写入 `api.update_settings`，通过托盘命令切换。

## 9. 调试

- 日志：`<数据目录>\logs\aideskpal.log`（写入失败时回退到系统临时目录）。
- 拖盘中右键"查看日志"，或设置 → 插件 → 打开插件目录。
- 修改插件后可以在设置 → 插件中重新保存/重启程序；宿主会在应用设置时重新加载插件。
- 可以用假宿主做单元测试，参考 `tests/test_plugins.py`。
