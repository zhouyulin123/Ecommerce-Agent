from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request

from app.infra.llm import LLMClient


class ImageGenerationTool:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(self, poster_spec: Dict[str, Any]) -> Dict[str, Any]:
        poster_prompt = poster_spec.get("poster_prompt", "")
        if not poster_prompt:
            return {}
        result = self.llm.generate_image(prompt=poster_prompt, negative_prompt="low quality, broken text, malformed hands, messy background")
        if not result or not result.get("url"):
            return result or {}
        local_path = self._download_to_current_dir(result["url"])
        if local_path:
            result["local_path"] = str(local_path)
            result["file_name"] = local_path.name
        return result

    @staticmethod
    def _download_to_current_dir(image_url: str) -> Optional[Path]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path.cwd() / "image"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"generated_image_{timestamp}.png"
        req = request.Request(image_url, method="GET")
        try:
            with request.urlopen(req, timeout=120) as resp:
                output_path.write_bytes(resp.read())
        except (error.URLError, error.HTTPError, TimeoutError, OSError):
            return None
        return output_path
