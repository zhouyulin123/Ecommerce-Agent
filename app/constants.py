"""项目级常量定义，统一维护节点名与通用配置。"""

# LangGraph 节点展示名称
FEEDBACK_PARSER_NODE = "Feedback Parser Node"
MESSAGE_PARSER_NODE = "Message Parser Node"
ROUTER_AGENT_NODE = "Router Agent"
QUERY_PLANNER_NODE = "Query Planner Node"
SQL_QUERY_NODE = "SQL Query Node"
USER_INSIGHT_NODE = "User Insight Node"
AUDIENCE_SELECTION_NODE = "Audience Selection Node"
COPYWRITING_NODE = "Copywriting Node"
POSTER_PROMPT_NODE = "Poster Prompt Node"
IMAGE_GENERATION_NODE = "Image Generation Node"

# 允许执行的业务节点集合（用于路由校验）
EXECUTION_NODES = {
    SQL_QUERY_NODE,
    USER_INSIGHT_NODE,
    AUDIENCE_SELECTION_NODE,
    COPYWRITING_NODE,
    POSTER_PROMPT_NODE,
    IMAGE_GENERATION_NODE,
}

# 地址归一化时会移除的行政区划后缀
LOCATION_MARKERS = ("特别行政区", "自治区", "省", "市")
