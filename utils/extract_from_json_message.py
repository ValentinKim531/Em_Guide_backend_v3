import json
from utils.logging_config import get_logger


logger = get_logger(name="extract_from_json_message")


def extract_json_from_response(response_text: str):
    """
    Извлекает JSON из текста ответа GPT.
    """

    try:
        json_start = response_text.find("```json")
        json_end = response_text.rfind("```")
        if json_start != -1 and json_end != -1:
            json_data = response_text[json_start + len("```json"):json_end].strip()
            return json.loads(json_data)
    except Exception as e:
        logger.error(f"Error extracting JSON from response: {e}")

    return response_text


def extract_text_before_json(response_text: str) -> str:
    """
    Извлекает текст из ответа до блока JSON.
    """

    if "```json" in response_text:
        try:
            json_start = response_text.find("```json")
            if json_start != -1:
                return response_text[:json_start].strip()  # Возвращаем текст до блока JSON
        except Exception as e:
            logger.error(f"Error extracting text before JSON: {e}")
    else:
        return response_text
