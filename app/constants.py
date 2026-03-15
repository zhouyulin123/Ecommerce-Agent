"""工作流角色、任务和兼容节点名称常量。"""

# Legacy node labels kept for prompt compatibility and trace output.
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

# High-level agent roles.
SUPERVISOR_AGENT = "Supervisor Agent"
PLANNER_AGENT = "Planner"
EXECUTOR_NODE = "Executor"
DATA_AGENT = "Data Agent"
WRITING_AGENT = "Writing Agent"
CREATIVE_AGENT = "Creative Agent"
RESPONSE_AGENT = "Response Agent"

# Executable task names.
TASK_ANALYZE_USER = "analyze_user"
TASK_SELECT_AUDIENCE = "select_audience"
TASK_WRITE_COPY = "write_copy"
TASK_PREPARE_POSTER = "prepare_poster"
TASK_GENERATE_IMAGE = "generate_image"

# Legacy execution nodes preserved for prompt validation.
EXECUTION_NODES = {
    SQL_QUERY_NODE,
    USER_INSIGHT_NODE,
    AUDIENCE_SELECTION_NODE,
    COPYWRITING_NODE,
    POSTER_PROMPT_NODE,
    IMAGE_GENERATION_NODE,
}

TASK_TO_AGENT = {
    TASK_ANALYZE_USER: DATA_AGENT,
    TASK_SELECT_AUDIENCE: DATA_AGENT,
    TASK_WRITE_COPY: WRITING_AGENT,
    TASK_PREPARE_POSTER: CREATIVE_AGENT,
    TASK_GENERATE_IMAGE: CREATIVE_AGENT,
}

LEGACY_NODE_TO_TASK = {
    SQL_QUERY_NODE: TASK_ANALYZE_USER,
    USER_INSIGHT_NODE: TASK_ANALYZE_USER,
    AUDIENCE_SELECTION_NODE: TASK_SELECT_AUDIENCE,
    COPYWRITING_NODE: TASK_WRITE_COPY,
    POSTER_PROMPT_NODE: TASK_PREPARE_POSTER,
    IMAGE_GENERATION_NODE: TASK_GENERATE_IMAGE,
}

# Markers removed during location normalization.
LOCATION_MARKERS = ("特别行政区", "自治区", "省", "市")
