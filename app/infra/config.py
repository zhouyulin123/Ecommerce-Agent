import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """从项目根目录 `.env` 读取环境变量，只补充未设置项。"""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _normalize_openai_base(url: str) -> str:
    """规范化 OpenAI 兼容接口地址，确保携带 `/v1/`。"""
    normalized = (url or "").strip()
    if not normalized:
        return ""
    if not normalized.endswith("/"):
        normalized += "/"
    if not normalized.rstrip("/").endswith("/v1") and not normalized.endswith("v1/"):
        normalized += "v1/"
    return normalized


@dataclass
class Settings:
    """项目运行时配置。"""

    openai_api_key: str
    openai_api_base: str
    openai_model: str
    openai_image_model: str
    enable_llm: bool
    enable_image_generation: bool
    database_url: str
    image_size: str
    image_cfg: float
    image_steps: int
    host: str
    port: int

    @property
    def llm_enabled(self) -> bool:
        """是否启用推理模型能力。"""
        return self.enable_llm and bool(self.openai_api_key and self.openai_api_base)

    @property
    def image_enabled(self) -> bool:
        """是否启用图像生成能力。"""
        return self.enable_image_generation and bool(
            self.openai_api_key and self.openai_api_base and self.openai_image_model
        )


def load_settings() -> Settings:
    """读取环境配置并构建 `Settings` 对象。"""
    _load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        database_url = "mysql+pymysql://root:123456@127.0.0.1:3306/Ecommerce_User_DB?charset=utf8mb4"

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "sk-nbflinobibhsbjbxaffcanczyfawlpzbbsrbdcoiixohcmfn").strip(),
        openai_api_base=_normalize_openai_base(os.getenv("OPENAI_API_BASE", "https://api.siliconflow.cn/")),
        openai_model=os.getenv("OPENAI_MODEL", "Pro/MiniMaxAI/MiniMax-M2.5").strip(),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "Qwen/Qwen-Image").strip(),
        enable_llm=os.getenv("ENABLE_LLM", "true").strip().lower() in {"1", "true", "yes", "on", "是", "对"},
        enable_image_generation=os.getenv("ENABLE_IMAGE_GENERATION", "true").strip().lower()
        in {"1", "true", "yes", "on", "是", "对"},
        database_url=database_url,
        image_size=os.getenv("IMAGE_SIZE", "1328x1328").strip(),
        image_cfg=float(os.getenv("IMAGE_CFG", "4.0")),
        image_steps=int(os.getenv("IMAGE_STEPS", "50")),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
