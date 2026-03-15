from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """按名称加载提示词模板文本。"""
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
