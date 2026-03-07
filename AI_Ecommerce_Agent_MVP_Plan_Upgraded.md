# AI 电商营销 Agent项目计划书

## 1. 项目定位

本项目是一个 ** AI 电商营销 Agent 实现系统**。
目标不是一次性做复杂的营销中台，而是基于现有的三张 MySQL 表，先实现一套可以真正跑通、可以演示、可以继续迭代的营销 Agent 工作流。

系统支持运营人员直接输入自然语言任务，例如：

- “张三最近没怎么消费，看看他最近关注什么，给他写一条广告。”
- “最近羊毛衫打 6 折，看看谁最近在关注这个商品。”
- “帮我做一张羊毛衫 6 折的促销海报。”
- “看看西湖区最近谁在关注商务手表，按关注强度排一下。”

中间经过大模型拆解任务,规划,推理,工具调用，按任务动态决定，可以返回：

- 某个用户的行为分析结果
- 某个商品的目标用户群名单
- 一条广告文案
- 一份海报 Prompt
- 或者它们的组合

---

# 2. MVP 版本


## 2.1 只使用现有三张表

数据库：`Ecommerce_User_DB`

表：

- `User_info`
- `User_logs`
- `User_Buy`

## 2.2 暂不实现的内容

以下能力先不做，避免系统过重：

- 商品价格表 / 活动表 / 优惠券表
- 长期用户画像建模
- 用户价值分层
- A/B 测试
- 营销效果评估
- 真正消息发送
- 图像实际生成
- 多轮记忆
- 在线学习

## 2.3 MVP 的核心目标

这一版只做 4 件事：

1. **理解自然语言任务**
2. **查询并整理数据库信息**
3. **做轻量级用户/人群洞察**
4. **生成广告文案或海报 Prompt**

---

# 3. 当前数据基础

## 3.1 User_info

用户基础信息表。

| 字段 | 说明 |
|---|---|
| user_id | 用户 ID |
| user_name | 用户名 |
| phone | 手机号 |
| address | 用户所在地区 |

### 用途
- 根据用户名定位用户
- 根据地域做简单筛选
- 给人群名单补充地区信息

---

## 3.2 User_logs

用户浏览记录表。

| 字段 | 说明 |
|---|---|
| id | 浏览记录 ID |
| user_id | 用户 ID |
| user_name | 用户名 |
| shop_name | 店铺名 |
| item_name | 商品名 |
| enter_time | 进入时间 |
| exit_time | 退出时间 |

### 用途
- 查询最近浏览记录
- 统计关注最多的商品
- 做目标人群筛选
- 统计某商品最近被谁关注

---

## 3.3 User_Buy

用户购买记录表。

| 字段 | 说明 |
|---|---|
| id | 订单记录 ID |
| user_id | 用户 ID |
| user_name | 用户名 |
| shop_name | 店铺名 |
| item_name | 商品名 |
| enter_time | 下单时间 |
| exit_time | 支付完成时间 |

### 用途
- 查询最近购买记录
- 判断用户是否买过某商品
- 辅助判断“看了很多但没买”

---

# 4. MVP 总体架构

这一版不采用固定顺序链，而是采用 **Router + 条件节点** 的最小工作流。

```text
用户自然语言任务
        ↓
Router Agent
        ↓
更新 State（任务类型、参数、节点计划）
        ↓
按任务进入不同节点
   ├─ SQL Query Node
   ├─ User Insight Node
   ├─ Audience Selection Node
   ├─ Copywriting Node
   └─ Poster Prompt Node
        ↓
每个节点执行后更新 State
        ↓
按条件决定继续 / 返回 / 终止
```

系统不是“先规定一路跑到底”，而是：

- 先判断任务是什么
- 再决定需要哪些节点
- 每个节点执行后根据结果决定是否继续

---

# 5. State


原因是：哪怕只是最小系统，也必须处理以下情况：

- 用户名查不到
- 浏览记录为空
- 某商品近期无人关注
- SQL 执行失败
- 用户只要名单，不要广告
- 用户只要海报，不要文案

如果没有 State，你的系统就会变成一串硬编码调用，很难稳定。

## 5.1 建议的 State 结构

```json
{
  "request": "",
  "intent_type": "",
  "entities": {},
  "next_nodes": [],
  "query_result": null,
  "insight": null,
  "target_users": [],
  "ad_copy": null,
  "poster_spec": null,
  "error": null,
  "done": false
}
```

## 5.2 字段说明

- `request`：原始自然语言请求
- `intent_type`：Router 判定出的任务类型
- `entities`：抽取出的参数，如用户名、商品、折扣、地区
- `next_nodes`：接下来准备执行的节点
- `query_result`：数据库查询原始结果
- `insight`：用户洞察结果
- `target_users`：人群筛选结果
- `ad_copy`：广告文案结果
- `poster_spec`：海报 Prompt 和结构化视觉信息
- `error`：错误信息
- `done`：任务是否终止

---

# 6. 任务类型设计

为了让 Router 更稳，建议先固定任务类型集合。

## 6.1 single_user_query
只查某个用户，不生成广告。

### 示例
- 张三最近看了什么
- 李四最近有没有买过羊毛衫

---

## 6.2 single_user_ad
针对单个用户生成广告。

### 示例
- 张三最近没消费了，看看他最近关注什么，写条广告
- 看看李四最近最关心哪个商品，给他写个推送文案

---

## 6.3 audience_query
按商品筛选关注人群。

### 示例
- 最近谁在关注羊毛衫
- 西湖区最近谁看过商务手表

---

## 6.4 poster_generation
生成活动海报 Prompt。

### 示例
- 做一张羊毛衫 6 折海报
- 生成一个商务手表促销海报 Prompt

---

## 6.5 combined_task
组合任务。

### 示例
- 最近羊毛衫打 6 折，看看谁在关注这个商品，再做张海报
- 查张三最近最关心什么，再写广告并给出海报主题

---

# 7. Router Agent 设计

Router 是整个 MVP 的核心。

## 7.1 Router 的职责

Router 不做数据库查询，也不直接写广告。
它只做 3 件事：

1. **理解任务**
2. **抽取参数**
3. **决定下一步调用哪些节点**

## 7.2 Router 输入

原始自然语言请求。

### 示例 1
```text
张三最近没怎么消费，看看他最近关注什么，给他写一条广告
```

### 示例 2
```text
最近羊毛衫打 6 折，看看西湖区谁在关注这个商品
```

### 示例 3
```text
帮我做一张羊毛衫 6 折的促销海报
```

## 7.3 Router 输出

### 输出示例
```json
{
  "intent_type": "single_user_ad",
  "entities": {
    "user_name": "张三"
  },
  "next_nodes": [
    "SQL Query Node",
    "User Insight Node",
    "Copywriting Node"
  ]
}
```

或：

```json
{
  "intent_type": "combined_task",
  "entities": {
    "product_name": "羊毛衫",
    "discount": "6折",
    "location_scope": "西湖区"
  },
  "next_nodes": [
    "Audience Selection Node",
    "Poster Prompt Node"
  ]
}
```

## 7.4 Router Prompt

```text
你是电商营销任务路由 Agent。

你的任务：
1. 理解用户请求
2. 判断任务类型
3. 抽取关键参数
4. 给出下一步需要调用的节点

可选任务类型：
- single_user_query
- single_user_ad
- audience_query
- poster_generation
- combined_task

可选节点：
- SQL Query Node
- User Insight Node
- Audience Selection Node
- Copywriting Node
- Poster Prompt Node

输入：
{user_request}

输出 JSON：
{
  "intent_type": "",
  "entities": {},
  "next_nodes": []
}

要求：
1. 只保留当前任务真正需要的节点
2. 如果请求中出现用户名，提取为 user_name
3. 如果请求中出现商品，提取为 product_name
4. 如果请求中出现折扣，提取为 discount
5. 如果请求中出现地区，提取为 location_scope
6. 只输出合法 JSON
```

## 7.5 Router 的程序级校验

建议程序侧增加校验：

- `intent_type` 必须在预设类型中
- `next_nodes` 中的节点名必须合法
- 如果 `intent_type = single_user_ad`，至少应该包含 `SQL Query Node`
- 如果 `intent_type = poster_generation`，至少应该包含 `Poster Prompt Node`

---

# 8. SQL Query Node 设计

这是最基础的执行节点。

## 8.1 作用
根据 Router 输出的实体信息，生成 SQL 并执行，返回原始查询结果。

## 8.2 适用场景
- 查某个用户最近浏览了什么
- 查某个用户最近买了什么
- 为用户洞察节点准备原始数据

## 8.3 输入

```json
{
  "intent_type": "single_user_ad",
  "entities": {
    "user_name": "张三"
  }
}
```

## 8.4 输出

```json
{
  "user_info": {
    "user_id": 12,
    "user_name": "张三",
    "address": "西湖区"
  },
  "recent_views": [
    {"item_name": "羊毛衫", "enter_time": "2026-03-01 10:00:00"},
    {"item_name": "商务手表", "enter_time": "2026-02-28 19:20:00"}
  ],
  "recent_buys": [
    {"item_name": "商务手表", "enter_time": "2026-02-20 12:00:00"}
  ]
}
```

## 8.5 建议查询项

### 1）查询用户基础信息
```sql
SELECT user_id, user_name, phone, address
FROM User_info
WHERE user_name = '张三'
LIMIT 1;
```

### 2）查询最近浏览
```sql
SELECT item_name, shop_name, enter_time
FROM User_logs
WHERE user_name = '张三'
ORDER BY enter_time DESC
LIMIT 10;
```

### 3）查询最近购买
```sql
SELECT item_name, shop_name, enter_time
FROM User_Buy
WHERE user_name = '张三'
ORDER BY enter_time DESC
LIMIT 10;
```

## 8.6 NL2SQL Prompt

```text
数据库名：Ecommerce_User_DB

表结构：
User_info(user_id, user_name, phone, address)
User_logs(id, user_id, user_name, shop_name, item_name, enter_time, exit_time)
User_Buy(id, user_id, user_name, shop_name, item_name, enter_time, exit_time)

你的任务：
根据输入需求生成 SQL。

要求：
1. 只允许 SELECT
2. 只能使用上述表和字段
3. 优先生成简单、稳定、可执行的 SQL
4. 如果需要多个查询，可以分别生成
5. 输出必须是合法 JSON

输入：
{query_request}

输出 JSON：
{
  "sql_list": [
    {
      "purpose": "",
      "sql": ""
    }
  ]
}
```

## 8.7 SQL 重试机制

这一版虽然是 MVP，但建议保留最小反思循环。

### 执行流程
1. LLM 生成 SQL
2. 程序做安全检查
3. 执行 SQL
4. 若执行失败，将错误信息回传给 LLM 修正
5. 最多重试 3 次

## 8.8 SQL 安全规则

- 只允许 `SELECT`
- 拒绝 `INSERT / UPDATE / DELETE / DROP / ALTER`
- SQL 长度超过阈值可拒绝
- 查询结果为空时不要报错，直接更新 State

## 8.9 查询后的条件分支

### 情况 A：用户存在
继续进入 `User Insight Node`

### 情况 B：用户不存在
直接写入：

```json
{
  "error": "未查到该用户"
}
```

并终止流程。

---

# 9. User Insight Node 设计

这一版把“行为分析 + 简单标签 + 轻量建议”合并为一个节点，避免中间层过多。

## 9.1 作用
根据最近浏览和最近购买，输出用户关注重点和可用于营销的简洁结论。

## 9.2 为什么要合并
MVP 只有三张表，数据维度较低。
没必要再拆成：

- Behavior Analysis Agent
- Profiling Agent
- Strategy Agent

直接一次性输出“洞察结果”更稳、更快。

## 9.3 输入

```json
{
  "recent_views": [
    {"item_name": "羊毛衫"},
    {"item_name": "羊毛衫"},
    {"item_name": "商务手表"},
    {"item_name": "羊毛衫"}
  ],
  "recent_buys": [
    {"item_name": "商务手表"}
  ]
}
```

## 9.4 输出

```json
{
  "top_interest": "羊毛衫",
  "view_not_buy": ["羊毛衫"],
  "summary": "用户近期多次浏览羊毛衫，但尚未购买，适合围绕该商品做轻量召回。"
}
```

## 9.5 Prompt

```text
你是电商用户洞察节点。

请根据用户最近的浏览记录和购买记录，输出轻量级洞察结果。

输入：
{behavior_data}

输出 JSON：
{
  "top_interest": "",
  "view_not_buy": [],
  "summary": ""
}

要求：
1. 只基于输入数据分析
2. 优先找出浏览最多的商品
3. 如果某商品浏览多但没有购买，放入 view_not_buy
4. summary 保持简短清晰
5. 只输出合法 JSON
```

## 9.6 条件分支

### 情况 A：recent_views 非空
正常产出洞察

### 情况 B：recent_views 为空
更新 State：

```json
{
  "insight": {
    "top_interest": "",
    "view_not_buy": [],
    "summary": "该用户近期没有可用浏览记录。"
  }
}
```

然后：
- 如果只是查询任务，可直接返回
- 如果是广告任务，可走一个兜底文案，或直接提示“缺少足够行为数据”

---

# 10. Audience Selection Node 设计

## 10.1 作用
根据商品名、地区等条件，从浏览表中筛选目标用户。

## 10.2 适用场景
- 最近谁在关注羊毛衫
- 西湖区最近谁看过商务手表
- 最近谁在关注某个折扣商品

## 10.3 输入

```json
{
  "product_name": "羊毛衫",
  "location_scope": "西湖区"
}
```

## 10.4 输出

```json
{
  "target_users": [
    {"user_name": "张三", "address": "西湖区", "view_count": 3},
    {"user_name": "李四", "address": "西湖区", "view_count": 2}
  ]
}
```

## 10.5 SQL 模板

### 不带地区
```sql
SELECT ui.user_name, ui.address, COUNT(*) AS view_count
FROM User_logs ul
JOIN User_info ui ON ul.user_id = ui.user_id
WHERE ul.item_name = '羊毛衫'
GROUP BY ui.user_name, ui.address
ORDER BY view_count DESC
LIMIT 20;
```

### 带地区
```sql
SELECT ui.user_name, ui.address, COUNT(*) AS view_count
FROM User_logs ul
JOIN User_info ui ON ul.user_id = ui.user_id
WHERE ul.item_name = '羊毛衫'
  AND ui.address = '西湖区'
GROUP BY ui.user_name, ui.address
ORDER BY view_count DESC
LIMIT 20;
```

## 10.6 Prompt

```text
你是电商目标人群筛选节点。

数据库表：
User_info(user_id, user_name, phone, address)
User_logs(id, user_id, user_name, shop_name, item_name, enter_time, exit_time)

你的任务是根据商品名和可选地区，生成筛选目标用户的 SQL。

输入：
{audience_request}

输出 JSON：
{
  "sql": ""
}

要求：
1. 只使用 SELECT
2. 必须统计每个用户对该商品的浏览次数
3. 如果地区为空，不要加地区过滤
4. 只输出合法 JSON
```

## 10.7 条件分支

### 情况 A：查到用户
正常返回名单

### 情况 B：名单为空
更新 State：

```json
{
  "target_users": [],
  "error": "当前条件下未找到关注该商品的用户"
}
```

然后：
- 如果任务只是查人群，直接返回
- 如果任务后面要做海报，也可以继续做，因为海报不依赖名单存在

---

# 11. Copywriting Node 设计

## 11.1 作用
根据用户洞察或活动信息，生成一条简洁广告文案。

## 11.2 适用场景
- 给单个用户写广告
- 给某个商品活动生成标题和副标题

## 11.3 输入模式

### 模式 A：用户广告
```json
{
  "product": "羊毛衫",
  "insight": "用户近期多次浏览羊毛衫，但尚未购买"
}
```

### 模式 B：活动广告
```json
{
  "product": "羊毛衫",
  "discount": "6折"
}
```

## 11.4 输出

```json
{
  "title": "你关注的羊毛衫降价了",
  "subtitle": "精选款限时优惠，现在入手更划算",
  "cta": "立即查看"
}
```

## 11.5 Prompt

```text
你是电商广告文案生成节点。

请根据输入生成一套营销文案。

输入：
{copy_input}

输出 JSON：
{
  "title": "",
  "subtitle": "",
  "cta": ""
}

要求：
1. 标题尽量控制在 18 字以内
2. 副标题尽量控制在 35 字以内
3. CTA 要简短，如“立即查看”“马上抢购”
4. 文案自然，不要夸张
5. 只输出合法 JSON
```

## 11.6 条件分支

### 情况 A：有明确商品
正常生成文案

### 情况 B：没有明确商品
使用兜底表达，例如：

```json
{
  "title": "你最近关注的好物有新动态",
  "subtitle": "现在看看，也许正有适合你的优惠",
  "cta": "立即查看"
}
```

---

# 12. Poster Prompt Node 设计

## 12.1 作用
输出图片模型可用的促销海报 Prompt，同时附带基础视觉结构信息。

## 12.2 为什么不只返回一段大文本
即便 MVP 不实际接图像引擎，也建议保留最少结构化字段，方便后续对接。

## 12.3 输入

```json
{
  "product": "羊毛衫",
  "discount": "6折",
  "title": "羊毛衫限时 6 折",
  "subtitle": "精选秋冬款现在入手更划算"
}
```

## 12.4 输出

```json
{
  "poster_prompt": "电商促销海报，主题为羊毛衫 6 折，秋冬氛围，暖色调，突出商品展示和折扣标签。",
  "visual_elements": ["羊毛衫", "折扣标签", "秋冬背景"],
  "color_palette": "暖色系"
}
```

## 12.5 Prompt

```text
你是电商海报 Prompt 生成节点。

请根据商品、折扣和文案信息，生成一个适合图片模型的中文海报 Prompt。

输入：
{poster_input}

输出 JSON：
{
  "poster_prompt": "",
  "visual_elements": [],
  "color_palette": ""
}

要求：
1. poster_prompt 必须完整可读
2. visual_elements 至少包含商品主体
3. color_palette 给出简单色调建议
4. 只输出合法 JSON
```

## 12.6 条件分支

### 情况 A：有商品 + 折扣
生成标准促销海报

### 情况 B：只有商品，没有折扣
生成商品主题海报

### 情况 C：只有折扣，没有商品
使用兜底表达，但这种情况尽量提示参数不足

---

# 13. 工具设计

MVP 只保留一个真正必须的工具：

## 13.1 mysql_query_tool

### 功能
执行 SQL 并返回结果。

### 输入
```json
{
  "sql": "SELECT * FROM User_info LIMIT 5;"
}
```

### 输出
```json
{
  "status": "success",
  "rows": [
    {
      "user_id": 1,
      "user_name": "张三",
      "phone": "13800138000",
      "address": "西湖区"
    }
  ]
}
```

### 规则
- 只允许 SELECT
- 执行异常时返回错误信息
- 支持 SQL 重试循环

---

# 14. MVP 节点关系与执行逻辑

## 14.1 单用户广告链

```text
Router Agent
   ↓
SQL Query Node
   ↓（若用户存在）
User Insight Node
   ↓（若有商品洞察）
Copywriting Node
   ↓
返回广告结果
```

### 中断条件
- 用户不存在 → 直接返回“未查到该用户”
- 无浏览记录 → 可返回分析结果，也可走兜底文案

---

## 14.2 人群查询链

```text
Router Agent
   ↓
Audience Selection Node
   ↓
返回目标用户群
```

### 中断条件
- 没有任何关注用户 → 直接返回空名单 + 提示

---

## 14.3 海报链

```text
Router Agent
   ↓
Poster Prompt Node
   ↓
返回海报 Prompt
```

适用于：
- 单独生成促销海报
- 不依赖数据库的简单海报任务

---

## 14.4 人群 + 海报组合链

```text
Router Agent
   ↓
Audience Selection Node
   ↓
Poster Prompt Node
   ↓
返回人群名单 + 海报 Prompt
```

说明：
名单为空时也可以继续做海报，因为海报本身不依赖名单存在。

---

# 15. SQL 与节点的错误处理

## 15.1 SQL 执行错误
若 `mysql_query_tool` 返回错误：

- 将错误信息注入 NL2SQL Prompt
- 让 LLM 修复 SQL
- 最多重试 3 次

失败后更新：

```json
{
  "error": "SQL 执行失败"
}
```

并终止。

## 15.2 查询结果为空
查询结果为空不视为系统报错，而是业务上的“查无结果”。
例如：

- 没有这个用户
- 没有人关注该商品
- 该用户没有浏览记录

这类场景应该走正常分支返回，而不是报异常。

## 15.3 JSON 输出校验
建议每个节点输出后做一次校验：

- 是否为合法 JSON
- 必填字段是否存在
- 空值是否可接受
- 类型是否正确

---

# 16. 推荐工程目录结构

```text
project/
├─ main.py
├─ agents/
│  ├─ router_agent.py
│  ├─ sql_query_node.py
│  ├─ user_insight_node.py
│  ├─ audience_selection_node.py
│  ├─ copywriting_node.py
│  └─ poster_prompt_node.py
├─ tools/
│  └─ mysql_query_tool.py
├─ prompts/
│  ├─ router.txt
│  ├─ nl2sql.txt
│  ├─ user_insight.txt
│  ├─ copywriting.txt
│  └─ poster_prompt.txt
└─ config/
   └─ db_config.py
```
