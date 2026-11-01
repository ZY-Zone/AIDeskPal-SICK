# 长期向量记忆 / Long-term memory

AIDeskPal-SICK 把「短期对话上下文」和「长期记忆」分开：

- `memory.json`：最近对话、动作、亲密度和事件，短窗口、随会话更新。
- `long_term_memory.sqlite3`：Planner 筛选后的长期摘要与向量索引，跨启动保留。

## 1. 写入什么

长期记忆不再自动保存原始对话，也不是每条用户消息都会写入。每轮首先由 Planner 判断：

1. 当前内容是否包含值得跨会话保留的稳定偏好、经历或约定；
2. 如果需要写入，Planner 返回简短、去敏的 `memory_write` 摘要和重要度；
3. 宿主只对这份摘要调用 `remember_summary()`，不会把整段对话或原始感知记录发送给 Embedding。

例如，用户说“记住我喜欢蓝色”时，写入内容应类似：

```text
用户喜欢蓝色。
```

近期对话仍按原有规则写入短期 `memory.json`，用于近期上下文；它与长期摘要写入是两条独立路径。命中密码、API Key、token、身份证、银行卡等敏感内容的摘要会在 Embedding/网络访问前被拒绝。

## 2. 向量检索与按需召回

默认使用 **OpenAI 兼容** 的 Embeddings 接口：

```http
POST {embedding_base_url}/embeddings
Authorization: Bearer {key}
{"model": "text-embedding-3-small", "input": "…"}
```

配置位置：**设置 → AI 大脑 → 长期向量记忆**。

- `Embedding Base URL`：留空时使用上面的 AI Base URL。
- `Embedding 模型`：例如 `text-embedding-3-small`、`text-embedding-3-large`；本地兼容服务也可填自己的模型名。
- `Embedding API Key`：留空时使用 AI API Key。
- `召回数量`：每次注入上下文的相关记忆条数。

首轮 Planner 不携带长期记忆。只有 Planner 返回 `should_recall=true` 时，宿主才用 `recall_query` 检索一次，然后让 Planner 复核一次；不会因每轮对话无条件召回，也不会循环重复召回。`MemoryRetriever` 会在代码层强制「每轮一次」的预算，模型即使重复请求也不会产生第二次检索。

如果接口不可用（例如聊天服务商不提供 embeddings、网络错误或没有 Key），会自动回退到 **本地 384 维特征哈希向量**，不需要下载模型。两种向量分别按维度比较；切换服务后旧记录不会丢失，只是按各自的向量空间召回。失败后进入 300 秒冷却，避免每轮都等一次超时。

向量化由 `src/aideskpal/ai/embedding.py` 的 `EmbeddingService` 统一提供，长期记忆、动作检索和语感检索共用同一模型、同一缓存与同一冷却状态；它不会抛异常，调用方永远拿到可用向量。

只有 Planner 请求的召回查询和 Planner 筛选的写入摘要可能发送给 Embedding 服务商。介意时请关闭长期记忆或使用本地兼容服务。

## 3. 上下文注入

召回结果以 `long_term_memory` 字段进入 `AIContext`，并带有 `memory_recall_performed=true`：

```json
{
  "long_term_memory": [
    {"kind": "planner", "text": "用户喜欢蓝色。", "score": 0.82}
  ],
  "memory_recall_performed": true
}
```

复核后的 Planner 决策、Replier 和 Actor 可以使用这些结果。提示词要求代理只在相关时自然使用，不逐条复述记忆、不把推测当事实。Replier 和 Actor 不能自行绕过 Planner 读写长期记忆。

## 4. 管理

- 设置页显示长期记录数量、当前索引类型和摘要文本。
- 「刷新记忆」重新读取统计。
- 「清空长期记忆」删除长期摘要和向量索引，不可撤销。
- 默认上限 4000 条记录，超出按重要度和时间裁剪。
- 数据库位于 `<数据目录>/long_term_memory.sqlite3`，未加密；请按个人隐私需求管理。
- 托盘的「三代理思维过程」会显示每轮记忆意图、召回状态和写入摘要，但不显示原始提示词、密钥或模型隐藏推理。

## 5. 相关文件

- 运行管线：`src/aideskpal/ai/orchestrator.py`
- 长期记忆：`src/aideskpal/ai/long_memory.py`
- 共享 Embedding：`src/aideskpal/ai/embedding.py`
- 检索（动作/记忆）：`src/aideskpal/ai/retrieval.py`
- 语感表达库：`src/aideskpal/ai/expression.py`
- Planner 跨轮状态：`src/aideskpal/ai/planner.py` 的 `PlannerState`
- 上下文类型：`src/aideskpal/ai/types.py`
- 设置：`src/aideskpal/ui/settings_dialog.py`
- 配置：`src/aideskpal/config/__init__.py` 的 `MemoryConfig`，默认值在 `src/aideskpal/config/main-config.json`
