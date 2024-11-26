import asyncio
import json
from services.audio_text_processor import process_audio_and_text
from services.save_message_to_db import save_message_to_db
from services.yandex_service import synthesize_speech
from utils.logging_config import get_logger
from utils.redis_client import (
    get_user_dialogue_history,
    save_user_dialogue_history,
)
from services.openai_service import send_to_gpt
from models import Survey
from utils.config import ASSISTANT4_ID

logger = get_logger(name="process_message_barsik")


async def process_user_message_barsik(user_id: str, message: dict, db):
    """
    Обрабатывает сообщение пользователя, поддерживает диалог с GPT и сохраняет результаты опроса.
    """
    try:
        logger.info(f"initial_chat3")
        logger.info(f"message_text_from_server: {message}")

        dialogue_history = await get_user_dialogue_history(user_id)
        logger.info(f"dialogue_history: {dialogue_history}")

        # Инициализация диалога
        if message.get("text") == "initial_chat":
            dialogue_history = [{"role": "user", "content": "Здравствуйте"}]
            await save_user_dialogue_history(user_id, dialogue_history)

            gpt_response = await send_to_gpt(dialogue_history, instruction=ASSISTANT4_ID)

            text_for_synthesis = extract_text_before_json(gpt_response)
            asyncio.create_task(save_message_to_db(db, user_id, text_for_synthesis, False)) # noqa
            gpt_response_audio = await synthesize_speech(text_for_synthesis)
            dialogue_history.append({"role": "assistant", "content": text_for_synthesis})

            await save_user_dialogue_history(user_id, dialogue_history)

            return {
                "type": "response",
                "status": "success",
                "data": {"audio": gpt_response_audio},
            }
        # Обычное сообщение пользователя
        user_text = await process_audio_and_text(message, user_language="ru")
        await save_message_to_db(db, user_id, user_text, True)
        logger.info(f"user_text: {user_text}")

        dialogue_history.append({"role": "user", "content": user_text})
        gpt_response = await send_to_gpt(dialogue_history, instruction=ASSISTANT4_ID)

        text_for_synthesis = extract_text_before_json(gpt_response)
        asyncio.create_task(save_message_to_db(db, user_id, text_for_synthesis, False))  # noqa

        gpt_response_audio = await synthesize_speech(text_for_synthesis)
        dialogue_history.append({"role": "assistant", "content": text_for_synthesis})
        await save_user_dialogue_history(user_id, dialogue_history)

        # Проверяем, есть ли JSON в ответе от GPT
        if "```json" in gpt_response:
            json_data = extract_json_from_response(gpt_response)
            if json_data:
                text_for_synthesis = extract_text_before_json(gpt_response)
                gpt_response_audio = await synthesize_speech(text_for_synthesis)
                asyncio.create_task(save_survey_results(user_id, json_data, db))  # noqa
                return {
                    "type": "response",
                    "status": "success",
                    "data": {"audio": gpt_response_audio},
                }

        return {
            "type": "response",
            "status": "success",
            "data": {"audio": gpt_response_audio},
        }

    except Exception as e:
        logger.error(f"Error processing user message: {e}")
        return {
            "type": "response",
            "status": "error",
            "message": "Произошла ошибка при обработке сообщения.",
        }


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

async def save_survey_results(user_id: str, data: dict, db):
    """
    Сохраняет результаты опроса в базу данных.
    """
    try:
        survey_data = {
            "userid": user_id,
            "headache_today": data.get("headache_today"),
            "medicament_today": data.get("medicament_today"),
            "pain_intensity": data.get("pain_intensity") if isinstance(data.get("pain_intensity"), str) else str(data.get("pain_intensity")),
            "pain_area": data.get("pain_area"),
            "area_detail": data.get("area_detail"),
            "pain_type": data.get("pain_type"),
            "comments": data.get("comments"),
        }
        await db.add_entity(survey_data, Survey)
        logger.info(f"Survey results saved for user {user_id}")
    except Exception as e:
        logger.error(f"Error saving survey results to database: {e}")
