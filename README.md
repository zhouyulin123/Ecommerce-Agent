# AI Ecommerce Marketing Agent

这是一个基于 LangChain + LangGraph 的对话式电商营销 Agent 的最小实现，当前使用 MySQL 作为业务数据库。

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
## 当前能力

- 对话式任务入口
- 多 Agent 协作：
  - Router Agent  路由
  - Feedback Parser Agent 反馈解析
  - Query Planer Agent 解析自然语言制定查询计划
  - SQL Query Node SQL查询节点
  - User Insight Node  用户行为解析
  - Audience Selection Node 选择目标客户
  - Copywriting Node  学做节点
  - Poster Prompt Node 海报提示词制作节点
  - Image Generation Node 图像制作节点
  - Response Agent 回应Agent
  - Message parser Agent 做返回的消息解析
- 编排框架：
  - LangGraph `StateGraph`
  - LangChain `ChatOpenAI`

![框架图](./image/框架图.png)

## 数据库

- 业务数据直接来自 MySQL `Ecommerce_User_DB`,可通过配置信息
- 程序会自动创建会话记忆表来记录当前已会话情况：
  - `agent_sessions`
  - `agent_messages`

## 模型 换更强的模型推理、生成的效果会更好
- 推理模型 `MiniMax-M2.5`
- 文生图模型 `Qwen-Image`
- 目前成本问题用的硅基流动转接的Api,复用同一套 `OPENAI_API_KEY` 和 `OPENAI_API_BASE`
- 海报任务会先生成 `poster_prompt`，再尝试直接生成图片 URL，并保存到当前项目目录

## Prompt
- 目前提示词还没有很完善，主要先把流程跑通，可根据需求去修改

## 启动
1. 在 `.env` 中填写：
   - `DATABASE_URL`
   - `OPENAI_API_KEY`
   - 如需改图像模型，可改 `OPENAI_IMAGE_MODEL`
2. 启动服务

```bash
python main.py serve
```
## API

- `GET /health`
- `POST /api/chat`
- `GET /api/sessions/{session_id}`

海报任务响应会额外返回 `generated_image`，其中包含图片 URL、本地保存路径、模型名和生成参数。

## CLI 调试

```bash
python main.py chat --json --message "上海普陀区儿童积木有新产品了，帮我写个广告语，并告诉我我都需要给谁推送"
result1：
"""
建议推送给这些用户：吴欣瑶(上海市普陀区, 购买1次)、赵宁(上海市普陀区, 浏览1次)
广告语：普陀区儿童积木推荐 / 适合3-6岁宝宝，安全材质趣味拼搭，在家动手又动脑 / 了解详情
"""

python main.py chat --message "帮我做一张羊毛衫6折的促销海报，查看下上海地区我该给谁推送"
result2：
"""
建议推送给这些用户：褚亦(上海市闵行区, 购买1次)、费可诺(上海市浦东新区, 购买1次)、伍浩(上海市杨浦区, 购买1次)、喻彤雪(上海市徐汇区, 购买1次)、邹雅(上海市闵  区, 购买1次)、傅欣(上海市宝山区, 浏览1次)、
行区, 购买1次)、傅欣(上海市宝山区, 浏览1次)、魏辰(上海市黄浦区, 浏览1次)、倪浩(上海市黄浦区, 浏览1次)、任文(上海市宝山区, 浏览1次)、毕一(上海市嘉定区, 浏览1次)
广告语：羊毛衫6折起 / 上海限定·精选羊绒羊毛系列 / 立即查看
海报提示词已生成，建议配色：驼色、深酒红、金色、暖白、浅灰、墨绿点缀
"""
## 测试

```bash
python -m unittest tests.test_workflow
```
