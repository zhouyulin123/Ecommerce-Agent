# AI Ecommerce Marketing Multi-Agent 项目说明

这份说明文档已经切换到当前代码结构，对应的是重组后的多 Agent 版本，而不是旧的节点平铺版本。

## 当前项目核心定义

这是一个面向电商营销场景的多 Agent 协作系统，目标是让系统具备：

- 明确的 Agent 角色边界
- 明确的 Tool 使用边界
- 清晰的 State / Memory 管理方式
- 可扩展的目录结构与执行方式

## 当前采用的核心结构

```text
User / API / CLI
  -> MarketingWorkflow
  -> Supervisor Agent
  -> Planner Agent
  -> Executor
  -> Specialist Agents
     - Data Agent
     - Writing Agent
     - Creative Agent
     - Response Agent
  -> Memory Persist
```

## 当前目录结构

```text
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

## Agent 设计原则

### 1. Agent 不是简单节点

当前项目中的 Agent 不再定义为“固定执行步骤”，而是定义为：

- 有明确职责边界
- 有自己的上下文输入
- 有自己的产出物
- 只可调用自己的工具集合

### 2. Tool 不是全局开放

当前项目不是所有 Agent 共用所有 Tool，而是：

- `Data Agent` 只看到 `Data Toolbelt`
- `Creative Agent` 只看到 `Creative Toolbelt`
- `Writing Agent` 当前不直接访问数据库工具

这能降低模型误调用工具的概率，也让系统更像真实的多 Agent 协作框架。

### 3. State 与 Memory 分层

- `State` 负责当前任务现场
- `Memory` 负责跨轮会话上下文

这是系统能处理追问、修改、确认的关键。

## 当前执行模式

当前系统不是固定的线性流水线，而是：

1. `Supervisor Agent` 先理解请求并给出初始任务意图
2. `Planner Agent` 生成任务计划和查询计划
3. `Executor` 根据 `task_queue` 决定当前该由哪个 Agent 执行
4. 各 Agent 执行后更新状态
5. 队列为空后由 `Response Agent` 汇总输出

这意味着：

- 不需要查库时不会查库
- 不需要生图时不会生图
- 不需要写文案时不会写文案

## 当前主要产物

- 用户洞察
- 目标人群列表
- 广告文案
- 海报提示词
- 图片生成结果

## 当前文档入口

- 总说明： [README.md](/c:/Users/HP/Desktop/智能客服助手demo/README.md)
- 架构图与讲解： [docs/ARCHITECTURE.md](/c:/Users/HP/Desktop/智能客服助手demo/docs/ARCHITECTURE.md)

## 建议的对外表述

建议统一用这句话介绍项目：

> 这是一个面向电商营销场景的多 Agent 协作系统，通过 Supervisor、Planner、Executor 和多个 Specialist Agent 围绕共享状态协作完成用户分析、人群筛选、文案生成和海报生成任务。
