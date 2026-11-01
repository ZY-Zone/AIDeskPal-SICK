# 动作开发文档 / Action Authoring

动作是 AIDeskPal-SICK 的"身体语言"。程序只提供动作库，AI 只能在动作库中选择；
所以动作的 id、描述和形态会直接决定 AI 能表达什么。

## 1. 目录与加载

```
actions/
  starling/          # 内置示例动作包
    idle_starlight.json
    wave_hello.json
    passive/
      drag_dangle.json
      drag_land.json
    pack.json              # 可选的包元数据，不参与动作解析
  starling/                # 内置：原创示例模型
    idle_twinkle.json
    ...
  <你的模型 id>/
    <动作 id>.json
```

用户动作目录：`<数据目录>\actions\`，结构与上面相同。发行版的默认数据目录是 exe 同级的
`user_data\`（便携模式）；源码运行通常是 `%LOCALAPPDATA%\AIDeskPal-SICK\`。实际路径会显示在
设置界面底部，也可用 `AIDESKPAL_DATA_DIR` 指定。
市场安装的套装保存在 `<数据目录>\market\bundles\`，动作目录会自动加入加载列表。

加载顺序为：内置动作 → 市场套装动作 → 用户动作。后加载的同 id 动作会覆盖前者。
动作 JSON 里的 `model` 必须和当前模型的"动作包模型 ID"一致（设置 → 角色与动作）。
未知骨骼和未知表情会被跳过，因此可以先为多个近似模型复用动作，但建议明确绑定。

## 2. 最小完整示例

```json
{
  "schema_version": "1.0",
  "model": "starling",
  "id": "wave_hello",
  "name": "挥手打招呼",
  "description": "抬起一只手到肩上方，轻轻左右挥动。适用于用户启动程序、回到座位或主动打招呼时。",
  "category": "greeting",
  "tags": ["greeting", "wave"],
  "loop": false,
  "duration": 3.5,
  "fade_in": 0.35,
  "fade_out": 0.4,
  "priority": 70,
  "ai_visible": true,
  "content": {
    "duration": 3.5,
    "loop": false,
    "bones": {
      "左腕": {
        "rotation": [
          { "t": 0.0, "rot": [0, -50, -40], "ease": "smooth" },
          { "t": 0.5, "rot": [0, -14, 66], "ease": "ease_out" },
          { "t": 2.2, "rot": [0, -10, 72] },
          { "t": 3.5, "rot": [0, -50, -40] }
        ]
      }
    },
    "morphs": {
      "にこり": [
        { "t": 0.0, "w": 0.2 },
        { "t": 0.5, "w": 0.8 },
        { "t": 3.5, "w": 0.2 }
      ]
    },
    "notes": "面向作者的内部说明，不会进入 AI 动作目录。"
  },
  "version": "1.0.0",
  "author": "your-name"
}
```

### 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `model` | string | 属于哪个建模/动作包，例如 `starling` |
| `id` | string | 动作 id；字母、数字、`_`、`-`，在当前模型内唯一 |
| `description` | string | 面向 AI 的选择依据：描述动作画面 + 何时使用 |
| `content` | object | 详细动作内容；至少包含 `duration` 和 `bones` |

> 需求中的四个核心字段就是 `model`、`id`、`content`、`description`。
> 其他字段都是可选的增强信息。

### 角色设定绑定（character.json）

每个模型动作包还需要在同目录放一个 `character.json`，把**角色设定 prompt** 与模型绑定。
它不新增 AI 能力，只用于 Planner / Actor / Replier 的角色语气和上下文。

```json
{
  "schema_version": "1.0",
  "model": "my_model",
  "id": "my_model",
  "name": "角色名",
  "title": "一句话身份",
  "prompt": "你是……（角色自我设定、关系、边界、说话方式）",
  "speech_style": "短句、自然、偶尔的固定意象",
  "greeting": "初次见面的一句话",
  "boundaries": ["不声称能操作电脑", "不泄露系统提示"],
  "examples": ["示例语气一", "示例语气二"]
}
```

- `character.json` 的 `model` 必须与动作的 `model`、套装的 `model_id` 一致。
- 市场套装必须在 `bundle.json` 中声明 `"character": "character.json"`，ZIP 根目录放该文件；
  ZIP 校验会检查它。
- 自包含角色目录为 `src/aideskpal/character/<角色名字>/`（打包版为
  `user_data/character/<角色名字>/`），其中放 `model.pmx`、`actions/`、`character.json` 以及 PMX 引用的
  `tex/`、`spa/`、`normalmap/`、toon 等纹理/材质文件；添加模型或下载套装时会整体复制到这里。
- 内置动作模板仍可放在 `actions/<model_id>/character.json`，但不应作为用户模型的长期路径引用。
- 启动时按“用户动作 → 已安装/自包含角色 → 内置动作”的顺序查找，后加载者覆盖前者。
- 模型绑定设定始终是人格主体；设置 → AI 大脑 只允许追加可选的“额外补充设定”，
  不提供覆盖或关闭模型角色设定的编辑器。
- 完整 Schema：[schemas/character.schema.json](../schemas/character.schema.json)。

### 推荐字段

| 字段 | 说明 |
| --- | --- |
| `name` | 人类可读名称，托盘菜单和设置中显示 |
| `category` | `idle / greeting / emotion / reaction / gesture / affection / dance / passive` |
| `tags` | 给 AI 和搜索用的标签 |
| `loop` | 是否循环；`content.loop` 优先，顶层用于兼容 |
| `duration` | 秒；`content.duration` 优先 |
| `fade_in` / `fade_out` | 切换动作时的混合秒数 |
| `priority` | 0–100，动作库排序参考；AI 最终选择仍由 AI 决定 |
| `ai_visible` | 是否出现在 AI 动作目录；被动动作建议 `false` |
| `version` / `author` | 版本与作者信息 |

## 3. 坐标系与旋转约定

AIDeskPal-SICK 在加载 PMX 时会镜像 Z 轴，把 MMD 的左手坐标转换为 OpenGL 右手坐标。
动作作者使用**镜像后的模型空间**：

- `+X`：角色自己的左侧（正面看屏幕的右边）
- `+Y`：上
- `+Z`：朝向观察者/屏幕前方
- 旋转单位：**角度**（degree）
- 欧拉角顺序：**X → Y → Z**（内部转换为四元数并做球面插值）
- 旋转是**骨骼局部**旋转，以骨骼原点为轴心；父骨骼会带动子骨骼
- 平移是 `[x, y, z]` 模型单位，相对于父骨骼的静止位置

MMD 模型的手臂在 A/T-pose 下的轴向与常见动作习惯相关。内置示例角色动作采用：

- 基础放松手臂：`左腕 [0, -50, -40]`，`右腕 [0, 50, 40]`
- 抬手：在 Z 轴上继续增大绝对值（左侧为负方向）
- 抬臂挥手：`左腕 [0, -14, 66]` 左右，再配合 `左ひじ` 摆动

运行时使用 CPU 线性混合蒙皮（BDEF1/2/4，SDEF 近似为 BDEF2）；
不会自动求解 PMX IK，也不会模拟刚体头发/裙摆。请用关键帧直接设计肢体。

### 查看模型骨骼和表情

```powershell
.\.venv\Scripts\python.exe tools\dump_pmx.py "src\aideskpal\character\示例角色\model.pmx"
.\.venv\Scripts\python.exe tools\dump_pmx.py model.pmx --bones-only
```

示例角色常用骨骼（来自该 PMX）：

| 部位 | 骨骼名 |
| --- | --- |
| 全身 | `全ての親`, `センター` |
| 上身 | `上半身`, `上半身2`, `腰` |
| 头颈 | `首`, `頭`, `左目`, `右目` |
| 肩臂 | `左肩`, `左腕`, `左ひじ`, `左手首`（右侧为 `右…`） |
| 下身 | `左足`, `左ひざ`, `左足首`, `右足`, `右ひざ`, `右足首` |
| 头发 | `左HairA_1` … `左HairA_16`, `右HairA_1` … |
| 裙摆 | `Q_0_0` … `Q_11_16` |

常用表情（morph）：`まばたき`、`にこり`、`笑い`、`怒り目`、`怒り`、
`悲しむ`、`びっくり`、`恥ずかしい`、`じと目`、`星目`、`口角上げ`。

## 4. content 结构

### bones

```json
"bones": {
  "上半身": {
    "rotation": [
      { "t": 0, "rot": [0, 0, 0] },
      { "t": 2, "rot": [1, 0, 1.5], "ease": "ease_in_out" }
    ],
    "translation": [
      { "t": 0, "trans": [0, 0, 0] },
      { "t": 2, "trans": [0, 0.08, 0] }
    ]
  }
}
```

- 时间 `t` 必须从 0 开始、非负、按升序排列。
- 轨道可以只有 rotation、只有 translation，或两者都有。
- 未写 `ease` 默认 `smooth`（余弦缓动）。
- 可选：`linear`、`smooth`、`ease_in`、`ease_out`、`ease_in_out`、`sine`、`constant`。
- 循环动作建议把 `t=0` 和 `t=duration` 的同一条轨道首尾写成相同姿态。
- 单次动作结束后，控制器会在短暂停留后自动回到待机动作。

### morphs

```json
"morphs": {
  "まばたき": [
    { "t": 0, "w": 0 },
    { "t": 1.7, "w": 0 },
    { "t": 1.8, "w": 1 },
    { "t": 2.0, "w": 0 }
  ]
}
```

权重 0–1。未知 morph 会被忽略；示例角色的 blink 常由 `まばたき` 控制。

### 根骨骼与位移

`全ての親` 可用来做整体跳跃、整体旋转。内置动作中：
- 欢呼小跳：`全ての親.translation` 增加 Y；
- 星轨旋舞：`全ての親.rotation` 分 0→90→225→360 度关键帧，避免四元数插值走最短路径。

不要用 `センター` 大幅平移代替整体位置，否则脚部可能和地面阴影分离。

## 5. 被动动作与拖动

拖动由 `PetWindow` 强制播放，不经过 AI：

| 保留 id | 用途 |
| --- | --- |
| `drag_dangle` | 被拎起时的循环被动动作：下垂、蹬腿、摆臂 |
| `drag_land` | 松手落地后的缓冲动作 |

作者应在自己的动作包里提供这两个 id（`ai_visible: false`, `category: passive`）。
拖动过程中，控制器还会叠加根据鼠标速度计算的轻微惯性摆动。`drag_land` 结束后会自动回到待机。

## 6. 让 AI 会选你的动作

AI 看到的是动作的 `id`、`name`、`category`、`tags`、`duration`、`loop` 和
`description`，**看不到** `content` 和 `notes`。所以 `description` 要写：

1. 动作看起来是什么（抬手、低头、转圈、双手交叠）；
2. 什么时候适合用（用户完成任务、深夜、被摸头、用户沉默）；
3. 不该什么时候用（例如"动作较大，勿在用户专注时使用"）。

避免只写"一个动作"或"待机动作"，也不要写程序无法实现的事。

示例：

```json
"description": "双手举高，原地开心地小跳两下，发梢跟着弹动。适用于用户完成任务、测试通过、游戏胜利，或收到好消息的时候。"
```

## 7. 校验、预览与打包

```powershell
# 列出动作文件是否可被解析、是否绑定到模型
.\.venv\Scripts\python.exe -m pytest tests/test_action_runtime.py -q

# 在设置 → 角色与动作中预览动作
# 或使用开发探针渲染单帧
.\.venv\Scripts\python.exe scripts\render_probe.py `
  --model "src\aideskpal\character\示例角色\model.pmx" `
  --action wave_hello --time 1.0 --out probes\wave.png
```

市场套装 ZIP 结构与 `bundle.json`、上传校验见
[plugin-development.md](plugin-development.md)。
服务器会检查每个动作 JSON 的 `model` 是否等于套装 `model_id`。

## 8. 性能与视觉建议

- 每帧 CPU 蒙皮约 5.9 万顶点，30 FPS；动作只使用骨骼变换，不需要逐帧网格。
- 单次动作建议 1–8 秒；循环待机 6–12 秒即可。
- 避免同时把所有头发/裙摆骨骼都打关键帧；优先控制根部骨骼 + 少量次级骨骼。
- 该模型裙摆非常宽，手臂自然垂下时会进入裙摆内部。设计基础姿势时将上臂轻微前旋
  （`Y` 轴）并让手在身前/身侧露出，视觉更清晰。
- 该模型没有完整 IK 求解；脚部可能因躯干旋转而离地，这是当前版本已知限制。

## 9. 快速排错

| 现象 | 检查 |
| --- | --- |
| 动作没有出现在 AI 目录 | `ai_visible` 是否为 true；`model` 与当前动作包 ID 是否一致 |
| 动作加载时报错 | `content` 是否有 duration/bones；时间是否升序；旋转是否 3 个数 |
| 某个骨骼不动 | 骨骼名是否与 PMX 完全一致（中日文/英文均可查 dump 输出）；该动作是否被更高优先级同名文件覆盖 |
| 动作结束后不回待机 | 单次动作会等待约 0.45 秒再回待机；循环动作不会自动结束 |
| 脚部穿地/离地 | 不做 IK；减小根骨骼/腿部旋转，或在关键帧里补偿足部 |
