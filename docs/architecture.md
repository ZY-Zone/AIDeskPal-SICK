# 架构设计 / Architecture

## 1. 总览

```
┌────────────────────────────────────────────────────────────────────┐
│                         Windows 10+ desktop                        │
│                                                                    │
│  perceptions            runtime / Qt UI              AI pipeline   │
│  ┌────────────┐   ┌──────────────────────────┐   ┌──────────────┐  │
│  │ keyboard   │──▶│ PerceptionService        │──▶│ context      │  │
│  │ hook       │   │ foreground / idle        │   │ builder      │  │
│  └────────────┘   └──────────┬───────────────┘   │   │          │  │
│                              │                   │   ▼          │  │
│  ┌────────────┐   ┌──────────▼───────────────┐   │ Planner      │  │
│  │ PMX model  │──▶│ PmxRenderer (OpenGL 3.3) │   │   ▼          │  │
│  │ parser     │   │ CPU skinning / morphs    │   │ Actor        │  │
│  └────────────┘   └──────────▲───────────────┘   │   ▼          │  │
│                              │                   │ Replier      │  │
│  actions/*.json   ┌──────────┴───────────────┐   └──────┬───────┘  │
│  ────────────────▶│ ActionPlayer / overlays  │◀─────────┘          │
│                   └──────────┬───────────────┘                     │
│                              │                                     │
│                   ┌──────────▼───────────────┐    ┌─────────────┐  │
│                   │ PetWindow / Bubble / Tray│───▶│ Market      │  │
│                   │ Settings / Chat          │    │ client      │  │
│                   └──────────────────────────┘    └─────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

## 2. 模块划分

| 路径 | 职责 |
| --- | --- |
| `src/aideskpal/app.py` | QApplication、生命周期、调度、AI 线程桥、插件宿主 |
| `src/aideskpal/config/` | `main-config.json` 默认配置、DPAPI 密钥、用户覆盖 |
| `src/aideskpal/character/` | 自包含角色：PMX、动作 JSON、character.json（被 gitignore） |
| `src/aideskpal/character_store.py` | 角色复制、套装导入、按模型发现 |
| `src/aideskpal/ui/onboarding.py` | 首次启动 AI 设置与确认向导 |
| `src/aideskpal/pmx/` | PMX 2.0/2.1 解析、PMX 数据模型、骨骼/蒙皮 |
| `src/aideskpal/render/` | OpenGL 资源、GLSL、相机、纹理、PMX 渲染器 |
| `src/aideskpal/animation/` | 动作 JSON 解析、采样、混合、交叉淡入 |
| `src/aideskpal/ai/` | Planner/Actor/Replier、共享 Embedding、表达库、检索、LLM 客户端、上下文、记忆、离线人格 |
| `src/aideskpal/perception/` | 全局键盘统计、前台应用、空闲时间 |
| `src/aideskpal/plugins/` | 插件清单、权限门面、加载器、事件总线 |
| `src/aideskpal/market/` | 市场 HTTP 客户端、ZIP 安装器 |
| `src/aideskpal/ui/` | 桌宠窗口、气泡、聊天、pystray 托盘、设置窗口 |
| `assets/` | 应用图标 |
| `plugins/` | 本地插件目录（仓库不带插件） |
| `schemas/` | 动作、插件清单、套装清单的 JSON Schema |
| `docs/` | 开发与架构文档 |

动作与模型制作工具不随仓库发布：它们属于作者自用的开发脚本，二次开发者可按
`docs/action-authoring.md` 的动作格式自行实现。

## 3. PMX 与渲染

### 3.1 解析

`pmx/parser.py` 只依赖标准库和 NumPy：

- 严格校验文本长度、数量、索引边界；对不规范的尾部数据容忍。
- 支持 BDEF1/BDEF2/BDEF4/SDEF/QDEF 权重读取；SDEF 在蒙皮时按 BDEF2 近似。
- 忽略刚体和关节；不做物理。
- 解析材质、全部 morph 类型，但渲染只使用 vertex / UV / material / bone 等受影响部分。
- 显示帧按 PMX 2.0 的"每项自带类型字节"格式读取。

加载后 `PmxModel.to_render_space()`：

1. 镜像 Z 轴，把 MMD 左手坐标转换成 OpenGL 右手坐标；
2. 翻转 UV 的 V 轴，并配合图片上下翻转，使纹理方向正确；
3. 反转三角形绕序；
4. 重新计算包围盒。

加载末尾调用 `repair_known_rigging()` 做按模型限定的运行时权重修复。夏季 PMX 把右腿膝
以下的顶点大量绑到了大腿骨 `右足D`，而左腿同一高度由 `左ひざD` 驱动；两根骨相差一整级
父级，屈膝时错绑顶点会被甩出，裙摆和鞋饰随之撕裂。修复以左腿为参照推出膝线，把膝线以下
的 `右足D` 影响改判给 `右ひざD`，只改内存中的权重，不写回 PMX。

动作作者看到的坐标就是镜像后的坐标。

### 3.2 骨骼与蒙皮

`skeleton.Skeleton`：

- 骨架按父级拓扑排序；缺失/循环父级会被安全处理。
- 每根骨骼的局部变换为 `T(parent-relative offset + animation delta) · R`；
- 根骨骼包含自身位置和动作平移；
- 绑定矩阵的逆为 `T(-rest_position)`；
- 蒙皮矩阵 = `bone_world · inverse_bind`；
- 蒙皮在顶点着色器完成：骨骼矩阵写入 `RGBA32F` texture buffer，顶点携带
  `vec4` 骨骼索引/权重，最多 4 根骨骼线性混合；CPU 只上传约 28 KB 的矩阵调色板。
- 静态顶点/索引/权重不重复上传；morph 改变时才更新基座顶点 VBO。

当前不做 CPU/GPU IK、物理、SPA/PMD 兼容。也没有 MMD 的完整双四元数 QDEF
（QDEF 会按 BDEF4 权重近似）。

### 3.3 材质与着色

- 贴图由 Pillow 加载、翻转并上传为 `RGBA8`，支持 BMP/PNG/JPG/TGA 等。
- 以材质为单位 `glDrawElements`；不做透明物体排序，按 PMX 材质顺序绘制。
- 片元着色器提供：双色 toon 渐变、材质高光、边缘光、纹理 alpha、球面贴图
  （乘算/加算）、材质 ambient。
- 不使用 MMD 真实 toon 贴图（内置 `toon01.bmp` 等资源不在模型目录中），使用程序化双色阶。
- 光照使用暖色主光 + 冷色正面补光 + 材质环境光；1024×1024 深度图提供头发/衣摆自阴影，
  5×5 PCF 柔化，地面另有半透明接触阴影。
- 透明桌面由 `QOpenGLWindow` + alpha buffer 完成；60 FPS（16 ms 精确定时器 + 垂直同步），
  交叉淡化会对旧动作继续采样，并在混合权重上使用 smoothstep。
- 每 0.45 秒读取一次 framebuffer alpha，构建点击命中掩码；`WM_NCHITTEST` 根据掩码
  把透明像素返回 `HTTRANSPARENT`，实现"只有角色身体可点击"。鼠标拖拽在角色区域生效。

### 3.4 动作播放

`ActionPlayer` 无 Qt 依赖：

- `ActionClip.sample(t)` 采样骨骼 rotation/translation 与 morph 权重；
- 关键帧使用四元数球面插值（Euler 输入）；
- 动作切换用交叉淡入（从旧动作采样到新动作采样）；
- `drag_dangle` 与程序化惯性 overlay 叠加；
- 单次动作结束后由窗口层在 0.45 秒后切回待机；
- 支持循环动作、动作时长推断、未知骨骼/表情软忽略。

### 3.5 屏幕边缘行为

`ui/edge.py` 的 `EdgeController` 只负责环境行为：

- 按权重选择侧边/顶部/底部鸭子坐；下边缘固定为坐姿，与拖拽方向无关；
- 用 `QVariantAnimation` 移动透明窗口，不改变窗口方向；
- 用 renderer 的 `stage_roll_degrees` / `stage_yaw_degrees` / `stage_scale`
  做模型倾斜与缩放；所有边缘姿态都使用同一常规窗口尺寸；
- 贴边位置沿边自由：竖边记录 y、横边记录 x，吸附时只把另一轴拉到墙线；
- 拖动松手时按 alpha mask 估算角色可见比例，出界超过 20%（可见不足 80%）时按最近边吸附；
- 顶部/侧边按概率触发 `edge_fall` → 窗口下落 → `edge_land_sit` → `edge_bottom_sit`；
- 坐姿使用当前蒙皮网格的支撑面；侧站将上下双手对齐同一墙线并保持双脚在墙外，
  上挂使用手腕骨骼投影校准；
  动作每次推进后同步更新接触位置，落地期间持续保持支撑，而非只在首帧对齐；
- 舞台 roll/yaw/scale 与透明窗口宽高共用一条缓动时间线，退出时同样平滑恢复；
- 拖动、点击、托盘动作会中断边缘状态；设置中可关闭。

边缘动作 `ai_visible=false`，不会进入 AI 可选动作目录，AI 仍然只能选择普通动作。

### 收起桌宠（最小化到托盘）

`window.hide_trigger` 决定用什么手势把桌宠收起来：

| 取值 | 触发方式 |
| --- | --- |
| `double_click_body`（默认） | 双击角色身体；双击头部始终打开聊天输入框 |
| `double_right_click` | 在角色上右键双击 |
| `hotkey` | `window.hide_hotkey` 指定的全局快捷键（默认 `Ctrl+Alt+H`，由 `ui/hotkey.py` 用 `RegisterHotKey` 注册） |
| `off` | 不启用该功能 |

收起必须是**彻底**的：`DesktopPetApp.hide_pet()` 会一并隐藏气泡、聊天输入框，停掉边缘控制器
并清除姿态，最后调用 `_release_foreground()` 交还前台。所有可能弹气泡的路径
（AI 回复、`speak()`、聊天占位）都先经过 `_can_show_bubble()`，因此隐藏期间到达的回复不会
再把文本框留在桌面上。可从托盘「显示桌宠」恢复。

隐藏同时会告知 Planner（`AIOrchestrator.set_replier_available`）：

- 收起时传 `False`，恢复时传 `True`；全屏自动隐藏走同一条路径；
- `AIContext.replier_available` 每轮带入 context，`planner_system()` 会追加
  「本轮状态：Replier 不可用」段落，要求 `should_speak=false`、把想说的话写进
  `speech_goal` 留待恢复后表达，但照常做召回与记忆写入；
- `PlannerState` 记录状态本身与**一次性**变化提示（`replier_available` /
  `replier_notice`），因此 Planner 既知道当前能否说话，也知道「刚刚收起」「刚刚恢复」这次变化；
- `Orchestrator.run()` 在 Replier 不可用时直接跳过 Replier，trace 记为
  「Replier 不可用（桌宠已收起），本轮不出声」。

## 4. AI 运行流程

1. `PerceptionService` 每 10 秒刷新前台进程、窗口标题、空闲时间、键盘速率。
   排除应用/标题会标记为 `private`，不发送标题和进程名。
2. `app.py` 的调度器在 `tick_seconds` / `idle_tick_seconds` 到期时发起 AI turn，
   并受勿扰、主动性抽样、气泡占用、拖动状态、小时动作上限等约束。
3. `AIOrchestrator.run` 构建 `AIContext`：时间、空闲、应用分类、活动摘要、
   当前动作、短期记忆、用户限制，以及当前模型绑定的角色摘要。
4. **Planner**：作为角色的亲身体验者与主控，接收感知、用户输入、其他代理说明、动作目录，
   以及它自己的 `planner_state`（关系阶段、最近 3 轮意图/情绪、尚未收尾的话题）；
   输出情绪、候选动作、给 Replier/Actor 的建议简报，以及是否召回/写入长期记忆。
   状态有界（6 轮 / 3 个话题），只含模型自写的短摘要，不是隐藏对话记录。
5. **按需记忆复核**：只有 Planner 请求时才召回一次长期记忆，再让 Planner 复核一次。
   `MemoryRetriever` 每轮强制单次召回，避免循环模型把一轮变成多次网络往返；
   写入时仅把 Planner 筛选的摘要交给 Embedding，不自动保存原始对话。
6. **Actor**：参考 Planner 简报但独立决定最终动作。它看到的不是整库动作，而是
   `ActionRetriever` 按本轮情境（意图、情绪、应用、时段）向量检索出的候选，
   Planner 的候选 id 与当前动作被强制置顶，因此不会因检索噪声丢失明确建议；
   权限仍以完整允许列表为准，检索只能缩小提示词，不能放宽许可。
7. **Replier**：先由 `ExpressionLibrary` 从角色自己的 `examples` 里检索 3-4 条语感样例
   （按情绪加权），再据此生成最终台词、情绪和气泡样式；样例只作为语感证据下发，
   并明确要求不得照抄。
8. 宿主校验动作 id 与频率，播放动作/显示气泡，写入短期记忆，提交 Planner 状态，
   并保存本轮结构化决策摘要。
9. 用户直接发消息会跳过主动性抽样与勿扰限制，但语音关闭设置仍然有效。

### 三个代理与共享 Embedding

四个组件职责分开，互不越权：

| 组件 | 职责 | 不该做的事 |
| --- | --- | --- |
| Planner | 体验当前时刻、决定是否说话/行动、独占长期记忆的召回与写入意图、维护跨轮状态 | 不写逐字台词、不强制执行动作 |
| Actor | 从预筛候选中决定最终动作或 `none` | 不写台词、不扩大动作权限 |
| Replier | 结合语感样例决定最终台词与气泡样式 | 不决定动作、不改记忆 |
| Embedding | 统一的向量服务：动作检索、语感检索、记忆召回/写入共用同一模型与缓存 | 不做决策、不发起网络以外的副作用 |

`EmbeddingService` 是唯一的向量入口：远程 OpenAI 兼容 `/embeddings` 优先，失败后进入
300 秒冷却并回退本地 384 维特征哈希向量，带 512 条缓存，永不抛异常。因此断网时
检索与记忆仍然可用，只是退化为词面相似度。

三个角色使用独立的 LLM 客户端、系统提示和可配置模型名；当前共用 Base URL/API Key。
托盘的「三代理思维过程」显示这些摘要、信息交接、记忆意图、模型和耗时，不显示原始
提示词、密钥或模型隐藏推理。

所有 AI 请求在后台 `QThread` 中执行；主线程只负责 UI 与播放。AI 结果到达时若窗口已
销毁或拖动中，会安全忽略动作部分。

### 角色设定绑定

- 模型包提供 `character.json`，内含 `model`、`id`、`name`、`prompt`、
  `speech_style`、`greeting`、`boundaries`、`examples`。
- 启动时按“用户动作 → 已安装套装 → 内置动作”的顺序查找，后加载者覆盖前者；
  市场套装在 `bundle.json` 中声明 `"character": "character.json"`。
- 角色 prompt 进入 Planner/Replier 的系统提示；Actor 获得角色名和摘要；
  `AIContext` 也携带角色摘要，便于三个代理保持同一个人格。
- 核心安全规则始终优先于角色设定；角色 prompt 不能授予程序未提供的能力。
- 模型自带角色设定始终是人格主体；设置 → AI 大脑仅提供可选的“额外补充设定”和用户偏好，
  不提供覆盖或关闭模型角色设定的编辑器。

### 离线降级

没有 API Key、AI 关闭、网络错误时使用 `OfflineBrain`。它遵守相同输出契约：

- 直接消息按关键词选择动作 + 回复模板；
- 定时事件根据应用分类、空闲、时间选择安静陪伴/打盹/张望等；
- 不产生未经设计的动作、不执行程序能力之外的命令。

离线模式让首次运行不需要任何密钥即可看到完整桌宠体验。设置中可关闭
`offline_fallback`：关闭后，如果 AI 未配置或调用失败，桌宠会保持静止而不是由规则代选，
从而保证"具体做什么由 AI 决定"。

### 记忆与隐私

- `memory.json` 保存最近 40 条对话、最近 120 个事件、亲密度和动作时间戳（短期）。
- `long_term_memory.sqlite3` 保存 Planner 筛选的长期摘要和向量；只有 Planner 请求时才把
  召回结果写入 `AIContext.long_term`，复核后的 Planner、Actor、Replier 可以使用。
- 向量化统一由 `src/aideskpal/ai/embedding.py` 的 `EmbeddingService` 提供：动作检索、
  语感检索、记忆读写共用同一模型、同一缓存和同一失败冷却。
- Embedding 优先调用配置的 OpenAI 兼容 `/embeddings`；没有可用服务时回退本地 384 维
  特征哈希向量，不要求额外模型下载。只有 Planner 的召回查询和写入摘要会进入该流程。
- 长期记忆设置可查看并清空；短期最近对话仍按原有短窗口规则记录。
- 不保存原始按键内容，不保存完整的窗口标题历史；命中密码/API Key 等敏感词的消息不写入长期记忆。
- API Key 和 Embedding Key 使用 Windows DPAPI（当前用户）加密，不写入 `settings.json`。
- AI 上下文和记忆文本只发送给用户配置的 OpenAI 兼容服务商；设置界面和文档均有提示。
- 记忆数据库未加密，存放在便携 `user_data` 内；介意时可在设置中关闭或清空。

## 5. 插件与市场

- `PluginManager` 从三处扫描插件，调用 `setup(api)`，失败隔离。
- API 门面按 manifest 的权限声明拒绝调用；卸载时自动退订事件和托盘项。
- 插件可注册 JSON 动作；注册会被校验并持久化。
- 市场客户端使用 `cw_session` cookie / session token 访问 `/cwusr/api`。
- 安装器对 ZIP 做路径穿越、符号链接、大小、清单、PMX 头、动作 model 字段校验。
- 市场服务器不执行上传的插件，仅做静态检查；管理员审核后才上架。

## 6. 线程模型

| 线程 | 工作 |
| --- | --- |
| Qt 主线程 | OpenGL 渲染、动作播放、窗口/设置、感知快照读取、插件回调；pystray 菜单回调通过 Qt 信号回到这里 |
| pystray 线程 | 原生通知区图标、右键菜单、通知气泡 |
| AI 工作线程 | LLM HTTP 请求、记忆写入（带锁） |
| 键盘钩子线程 | WH_KEYBOARD_LL 消息泵与计数 |
| 感知线程 | 前台/空闲采样 |
| uvicorn 工作线程 | 同步文件/DB 操作，AI 客户端不涉及服务器 |

一次只运行一个 AI turn，用户消息在忙碌时最多排队 3 条。

## 7. 已知限制与后续方向

- 无物理（头发/裙摆随刚体）；动作作者需手动打关键帧。
- 无 IK 求解；脚部可能随上身动作离地。
- 无音频/TTS；语音可以作为插件或后续模块。
- 无 PMX 2.1 morph 的全部渲染支持（UV/material/bone morph 部分已解析但未全部应用）。
- 仅 Windows 10/11；Linux/macOS 仅能运行服务器与测试，感知钩子会禁用。
- 市场 HTTP 部署没有 TLS；正式公开运营前应配置 HTTPS。
- 上传/审核只做基础静态校验，不构成恶意代码检测。

## 8. 构建与分发

- 开发：`run.ps1` 创建 venv 并运行 `python -m aideskpal`。
- Windows 启动器：`src/aideskpal/start.vbs` 通过 UAC 以管理员身份启动。
  如果 `.venv` 不存在，先运行 `bootstrap.cmd` / `bootstrap.py`，在 Tk 引导窗口中安装依赖；
  安装完成后调用 `.venv\Scripts\pythonw.exe -m aideskpal`，并把
  `AIDESKPAL_DATA_DIR` 指向项目 `user_data/`。不打包 Python，也没有管理员 manifest。
- 模型本身不进入代码许可证；用户自有模型放在磁盘并由设置引用。
