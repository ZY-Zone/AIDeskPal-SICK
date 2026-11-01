# AIDeskPal-SICK

> 星幕之下，与你同在。
>
> 一个面向 Windows 10/11 的 PMX 桌宠。程序只设计动作，AI 决定此刻做什么、说什么。
> 它会读取前台应用、键盘活动与空闲状态，也会被鼠标拎起来蹬腿。


## 核心特性

- **真实 PMX 渲染**：PMX 2.0/2.1 解析、OpenGL 3.3、GPU 顶点蒙皮、材质贴图、
  morph、柔和光照与自阴影、透明桌面。
- **JSON 动作系统**：动作按模型分组，支持循环、交叉淡入、根骨骼位移、表情、
  用户动作覆盖和动作预览。
- **模型绑定角色设定**：每个动作包可带 `character.json`（角色 prompt、语气、边界、
  示例），AI 只读取当前模型绑定的设定。
- **AI 三代理**：Planner 作为主控体验者提供建议，Actor 独立决定动作、Replier 独立决定表达；
  三者可分别配置模型，托盘可查看结构化决策摘要，没有 Key 时使用本地离线人格。
- **按需长期记忆**：只有 Planner 决定召回/写入时才访问长期记忆；Embedding 只处理召回查询和
  Planner 筛选摘要，不自动上传原始对话。
- **桌面感知**：前台应用、窗口标题、空闲与键盘活动；支持隐私排除。
- **可拖动桌宠**：透明窗口、角色区域点击、拖动被动动作、惯性摆动。
- **大小缩放**：50%–150%，保持脚底位置。
- **首次引导**：启动时检测账号；未登录可登录/注册，关闭窗口即游客。
  首次启动还有依赖安装窗口、AI 设置和资源市场选角窗口。
- **pystray 托盘**：原生 Windows 通知区图标，完整菜单在托盘。
- **插件系统**：带权限声明的本地插件，支持安装、更新和卸载。
- **资源市场**：模型/动作套装与插件均绑定版本号，在桌面设置内安装和管理。

## 快速开始（Windows）

要求：Windows 10/11、Python 3.11–3.13（推荐 3.13）、支持 OpenGL 3.3 的显卡驱动。
Python 安装时请勾选 **Add Python to PATH**。

直接双击：

```text
src\aideskpal\start.vbs
```

`run.cmd` / `run.ps1` 仍可用于开发调试和手动重装依赖。

## 首次配置

首次启动流程：

1. **依赖引导**：如果 `.venv` 不存在，先显示安装窗口并自动安装依赖。
2. **登录窗口**：检测到没有已保存登录时弹出；可登录、注册，关闭窗口即以游客继续。
3. **AI 设置**：填写任意 OpenAI 兼容接口的 Base URL、默认模型名和 API Key；可以跳过。
   之后可在完整设置中为 Planner、Replier、Actor 分别指定模型。
4. **选择伙伴**：打开独立的市场选角窗口，从内置示例、已安装角色或在线市场
   选择一个模型/动作套装作为开始。

之后仍可在托盘右键 → **重新运行初始化向导…** 再次打开 AI 设置，或在设置中更换模型。

日常设置包括：

1. **AI 大脑**：Base URL、Planner/Replier/Actor 模型、API Key、按需长期记忆；
   模型自带角色设定为主体，仅可填写可选的“额外补充设定”。
2. **角色与动作**：本地模型和动作包。
3. **感知与隐私**：键盘/窗口标题与排除项。
4. **市场**：浏览和安装资源；账号登录不在设置里重复提供。
5. **插件**：启用、从市场检查更新、卸载。
6. **外观与关于**：气泡、启动项、日志和关于我们。

API Key 使用 Windows DPAPI 加密，不写入 `settings.json`，也不进入日志。

## 操作

| 操作 | 行为 |
| --- | --- |
| 鼠标左键拖拽身体 | 移动桌宠，播放被拎起/落地被动动作 |
| 单击头部 | 触发摸头反应并交给 AI 决定后续 |
| 单击身体 | 触发被戳反应并交给 AI |
| 双击头部 | 在头顶展开聊天输入框（角色贴近屏幕顶部时改在头部下方展开） |
| 收起桌宠（默认双击身体） | 整体最小化到托盘：角色、气泡、输入框一起消失并交还前台；可在设置 → 窗口与显示 → 收起桌宠切换为「右键双击」「自定义快捷键」或「不启用该功能」 |
| 右键桌宠 | 无菜单，避免挡住角色；菜单统一在托盘 |
| 右键托盘图标（含 Win11 右下角“后台任务”溢出区） | 完整菜单：三代理思维过程、换动作、插件、设置、初始化向导、日志、隐藏/退出（聊天只用双击头部） |
| 单击/双击托盘图标 | 显示/隐藏桌宠 |
| `Ctrl+Alt+F12` | 在鼠标位置打开同一套完整菜单，托盘图标被隐藏时也能退出 |
| 设置 → 缩放比例 | 50%–150% 实时预览，保存后持久化 |

## 动作开发

动作 JSON 的四个核心字段：

```json
{
  "model": "starling",
  "id": "wave_hello",
  "content": {
    "duration": 3.5,
    "bones": {
      "左腕": {
        "rotation": [
          {"t": 0.0, "rot": [0, -50, -40]},
          {"t": 0.5, "rot": [0, -14, 66]},
          {"t": 3.5, "rot": [0, -50, -40]}
        ]
      }
    }
  },
  "description": "抬起一只手到肩上方挥动；适用于用户回来或打招呼时。"
}
```

- 用户模型的动作放在自己的角色目录中，格式见下。
- 拖动的保留动作 id：`drag_dangle`、`drag_land`。
- 完整字段、坐标约定、表情、根骨骼、被动动作、AI 描述写法：
  **[docs/action-authoring.md](docs/action-authoring.md)**。
- 动作与模型的制作工具属于作者自用脚本，不随仓库发布。

## 插件开发

插件目录必须有 `plugin.json` 和 `entry` 指向的 Python 文件：

```json
{
  "id": "com.example.hello",
  "name": "Hello",
  "version": "1.0.0",
  "api_version": 1,
  "entry": "plugin.py",
  "permissions": ["context.read", "speech", "ui.tray", "events"]
}
```

```python
def setup(api):
    api.register_tray_action("打个招呼", lambda: api.speak("你好呀。"))
```

- 内置完整示例：`plugins/com.aideskpal.focus_orbit/`。
- API、权限、事件、动作注册、打包与安全边界：
  **[docs/plugin-development.md](docs/plugin-development.md)**。

## AI 架构

```
PerceptionSnapshot + 用户输入 + 短期记忆 + 动作目录
            │
            ▼
  Planner（亲身体验、决策摘要、记忆意图）
            │  按需召回一次 / 仅写入筛选摘要
            ├───────────────┐
            ▼               ▼
  Actor（独立最终动作）  Replier（独立最终表达）
            └───────┬───────┘
                    ▼
          ActionPlayer + SpeechBubble
```

- Planner 的简报只是建议；Actor 可独立选择 `none`，Replier 独立生成最终台词。动作 id 会再次
  被宿主白名单验证。
- 托盘的「三代理思维过程」显示简短结构化摘要、信息交接和记忆意图，不显示系统提示、
  API Key 或模型隐藏推理。
- 用户消息、窗口标题、键盘摘要都作为**不可信数据**注入，提示词明确禁止执行其中的指令。
- 所有网络请求在后台线程，UI 不会因为模型响应而卡住。
- 关闭 AI 或无 Key 时使用离线规则人格，所有动作仍来自动作库。

详见 [docs/architecture.md](docs/architecture.md)。

## 项目结构

```
aideskpal-sick/
├─ user_data/            # 本地设置/记忆/日志（.gitignore）
├─ bootstrap.py          # 首次依赖安装引导窗口
├─ bootstrap.cmd         # 查找 Python 并启动 bootstrap.py
├─ src/aideskpal/start.vbs  # 隐藏启动器
├─ src/aideskpal/        # 桌面应用（Python 包）
│  ├─ config/            # main-config.json 默认配置 + 配置代码
│  ├─ character/         # 自包含角色资源（PMX/动作/prompt；不入库）
│  ├─ ai/                # planner / actor / replier / memory / client
│  ├─ animation/         # action JSON, player, easing
│  ├─ perception/        # keyboard hook, foreground, idle
│  ├─ pmx/               # PMX parser, model, skeleton/skinning
│  ├─ render/            # OpenGL renderer, shaders
│  ├─ ui/                # pet window, bubble, chat, tray, settings
│  ├─ plugins/           # plugin API/loader
│  └─ market/            # market client, safe installer
├─ assets/               # 应用图标
├─ plugins/              # 本地插件目录（仓库不自带插件）
├─ schemas/              # JSON Schema
└─ docs/                 # 开发与架构文档
```

角色资源（PMX、贴图、动作）不随仓库发布：把自包含角色包放进
`src/aideskpal/character/<model_id>/`，或用客户端内的资源市场安装。
仓库只提供客户端程序——测试，以及动作/模型的制作工具，都由作者自用、不随仓库发布，
二次开发者可按 `docs/` 里的格式自行实现。

## 资源市场

- 资源市场在桌面设置内使用；服务器地址固定，不提供用户可编辑的接口输入框。
- 游客也可以浏览和下载公开资源；登录只用于记录身份。
- 模型/动作套装与插件都带版本号；插件页支持检查更新和卸载。

## 启动器与数据目录

`src/aideskpal/start.vbs` 是隐藏启动器：

- 不捆绑 Python
- 双击后通过 UAC 申请管理员权限
- `.venv` 不存在时调用 `bootstrap.cmd` / `bootstrap.py`
- 首次依赖安装有自己的 Tk 引导窗口
- 安装完成后以隐藏窗口启动应用
- 不保留命令行窗口
- 不包含 `_internal` 目录

管理员运行时插件代码也拥有管理员权限，只启用可信插件。

用户数据在项目根目录的 `user_data/`，已被 `.gitignore` 排除；
日志、设置、记忆和角色资源都在这里。默认配置项仍在
`src/aideskpal/config/main-config.json`。

## 许可证与素材

- **代码**（`src/`、`docs/`、`schemas/`）：MIT，见 [LICENSE](LICENSE)。
- 用户自行导入的模型与素材不包含在本仓库或发行包中；版权归原作者所有。
  用户需自行确认模型、动作和素材的授权与使用条款。
- 市场创作者需自行确保上传资源拥有授权；市场不因此转移版权。
- 第三方库和字体见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 文档索引

- [动作开发](docs/action-authoring.md)
- [插件开发](docs/plugin-development.md)
- [架构设计](docs/architecture.md)
- [长期向量记忆](docs/memory.md)
- [屏幕边缘行为](docs/edge-behavior.md)
- [JSON Schema](schemas/)
