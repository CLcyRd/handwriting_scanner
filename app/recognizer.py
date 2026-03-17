from pathlib import Path
import google.generativeai as genai


MODEL_NAME = "gemini-3.1-flash-lite-preview"


class GeminiRecognizer:
    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def recognize_page(self, image_path: Path, history: str, page_number: int, total_pages: int) -> str:
        prompt = (
            "你是一位擅长中文手稿识别与校对的助理。"
            "当前输入是一位中国老电影艺术家，谢晋，的手写日记或笔记扫描页。"
            f"正在处理第 {page_number} / {total_pages} 页。"
            "如果当前页有连笔、模糊或残缺字迹，请结合前文语境做合理推断。"
            "识别结果一律为简体中文，即使图片中是繁体字，也要转换为简体中文输出。"
            "识别结果为段落、列表或表格的格式。"
            "只输出最终识别文本，不要输出解释、标签或Markdown。"
            "以下是前文识别内容：\n"
            f"{history if history.strip() else '（无）'}"
        )
        image_part = {"mime_type": "image/png", "data": image_path.read_bytes()}
        response = self.model.generate_content([prompt, image_part])
        text = getattr(response, "text", "") or ""
        return text.strip()
