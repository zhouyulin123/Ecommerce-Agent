# 电商智能体工作台

这是一个面向电商营销场景的多 Agent 协作系统。项目已经不是单纯的后端编排，而是一个前后端一体的工作台：

- 后端：`Supervisor Agent -> Planner Agent -> Executor -> Specialist Agents -> Toolbelts`
- 前端：`Visual page` 电商营销工作台

系统目标不是只完成一次任务，而是把自然语言任务理解、任务规划、工具调用、执行步骤可视化、结果确认与二次修改串成完整闭环。

## 页面预览

![前端工作台预览](docs/images/frontend-workbench.png)

## 核心能力

- 用户行为理解
- 营销人群筛选
- 广告文案生成
- 海报提示词生成
- 图片生成
- 多会话管理
- 执行步骤可视化
- 会话记忆与二次修改

典型请求：

- `张三最近在看什么，帮我给他写一条广告文案`
- `最近谁在关注羊毛衫，筛出可推送用户`
- `帮我做一张羊毛衫 6 折海报`
- `上海地区最近谁在关注羊毛衫，顺便生成一版文案和海报`
- `这版海报很好，但背景换成更有春天感一点`

## 总体架构

```mermaid
flowchart TD
    UI[用户入口<br/>前端工作台 / API / CLI] --> API[FastAPI 路由层<br/>接口与静态页挂载]
    API --> WF[MarketingWorkflow<br/>系统总编排入口]

    WF <--> ST[状态<br/>当前任务现场]
    WF <--> MEM[记忆<br/>跨轮会话记忆]

    WF --> SA[Supervisor Agent<br/>理解目标 / 识别修改]
    SA --> PL[Planner Agent<br/>生成执行计划]
    PL --> EX[Executor<br/>按 task_queue 调度]

    EX --> DA[Data Agent<br/>用户分析 / 人群筛选]
    EX --> WA[Writing Agent<br/>广告文案生成]
    EX --> CA[Creative Agent<br/>海报 / 图片生成]
    EX --> RA[Response Agent<br/>组织最终回复]

    DA --> DT[数据工具集<br/>Data Agent 专属工具]
    CA --> CT[创意工具集<br/>Creative Agent 专属工具]

    DT --> SQL[SQLQueryTool<br/>查单用户行为]
    DT --> AUD[AudienceSelectionTool<br/>筛目标人群]
    CT --> IMG[ImageGenerationTool<br/>生成营销图片]

    API --> WB[Visual page 工作台<br/>历史会话 / 当前对话 / 执行过程 / 结果面板]
```

看图方式：

- `FastAPI` 同时提供接口和前端静态页
- `MarketingWorkflow` 是后端总入口
- `状态` 和 `记忆` 是 Agent 协作的上下文基础
- `Supervisor -> Planner -> Executor` 是上层编排链
- `Data / Writing / Creative / Response` 是领域执行 Agent
- 工具按 Agent 隔离，不是全局开放

## 前端工作台

前端目录：

- `Visual page/`

当前布局：

- 左侧：历史会话 + 新建任务
- 中间：当前对话 + 输入区
- 中间下半区：执行过程时间线
- 右侧：查询计划、人群结果、文案结果、海报与图片、记忆状态

前端职责：

- 展示历史会话并切换
- 发起新任务
- 终止当前等待中的请求
- 可视化 `execution_steps`
- 展示结构化结果卡片
- 承接二次修改和确认

核心文件：

- `Visual page/index.html`
- `Visual page/styles.css`
- `Visual page/app.js`

## Agent 边界

### Supervisor Agent

- 理解用户目标
- 识别新任务 / 修改 / 确认
- 抽取中间表示和任务方向

目录：

- `app/agents/supervisor/`

### Planner Agent

- 生成 `execution_plan`
- 生成 `query_plan`
- 规范化 `task_queue`

目录：

- `app/agents/planner/`

### Executor

- 根据 `task_queue` 调度下一个 Agent
- 不直接做业务理解

目录：

- `app/agents/executor/`

### Data Agent

- 查询单用户行为
- 筛选营销人群
- 生成轻量洞察

目录：

- `app/agents/data/`

### Writing Agent

- 生成广告文案
- 只消费结构化上下文，不直接访问数据库

目录：

- `app/agents/writing/`

### Creative Agent

- 生成海报提示词
- 调用图片生成工具

目录：

- `app/agents/creative/`

### Response Agent

- 汇总最终输出
- 组织面向用户的回复

目录：

- `app/agents/response/`

## Tool 设计

当前工具按 Agent 隔离，而不是全局共享：

- `Data Agent` 只使用 `数据工具集`
- `Creative Agent` 只使用 `创意工具集`
- `Writing Agent` 当前不直接访问数据库工具

调用方式：

- 每个 `toolbelt` 内部把工具封装成 LangChain `StructuredTool`
- Agent 通过 `LLMClient.choose_tool_call()` 调用 `bind_tools`
- 模型先选工具和参数，再由 Agent 执行工具
- 执行结果统一回写 `ToolCallRecord`
- 如果模型没有返回有效工具，则回退到默认工具

工具目录：

- `app/tools/base.py`
- `app/tools/data/`
- `app/tools/creative/`

## 状态与记忆

运行时核心文件：

- `app/runtime/state.py`
- `app/runtime/workflow.py`

关键概念：

- `状态`：当前任务现场
- `记忆`：跨轮会话上下文
- `ToolCallRecord`：工具调用轨迹
- `execution_steps`：执行步骤可视化数据

## 目录结构

```text
Visual page/
├─ index.html
├─ styles.css
├─ app.js
└─ README.md

app/
├─ runtime/
│  ├─ workflow.py
│  └─ state.py
├─ infra/
│  ├─ config.py
│  ├─ database.py
│  └─ llm.py
├─ agents/
│  ├─ supervisor/
│  ├─ planner/
│  ├─ executor/
│  ├─ data/
│  ├─ writing/
│  ├─ creative/
│  └─ response/
├─ tools/
│  ├─ base.py
│  ├─ data/
│  └─ creative/
├─ prompts/
├─ api/
└─ utils/
```

## 启动方式

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动前准备

在项目根目录创建 `.env`，至少补齐以下配置：

```env
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/Ecommerce_User_DB?charset=utf8mb4

OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=your_api_base
OPENAI_MODEL=your_text_model
OPENAI_IMAGE_MODEL=your_image_model

ENABLE_LLM=true
ENABLE_IMAGE_GENERATION=true
```

### 启动后端与前端工作台

```bash
python main.py serve
```

浏览器访问：

```text
http://127.0.0.1:8000/workbench/
```

### CLI 调用

```bash
python main.py chat --message "帮我写一条羊毛衫 6 折广告文案" --pretty
python main.py chat --message "看看谁在关注羊毛衫" --json
```

## API

- `GET /health`
- `POST /api/chat`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `DELETE /api/sessions/{session_id}`
- `GET /workbench/`

## 推荐阅读顺序

1. `app/runtime/workflow.py`
2. `app/runtime/state.py`
3. `app/agents/supervisor/agent.py`
4. `app/agents/planner/agent.py`
5. `app/agents/executor/agent.py`
6. `app/tools/`
7. `Visual page/`

## 补充文档

- 深入架构说明：`docs/ARCHITECTURE.md`

