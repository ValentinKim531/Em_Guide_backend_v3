import asyncio
from constants.assistants_answers_var import audio_code_repeat_request, audio_code_first_question, text_code_first_question
from services.audio_text_processor import process_audio_and_text
from services.save_message_to_db import save_message_to_db
from services.survey_service import save_survey_results
from services.yandex_service import synthesize_speech, synthesize_speech_with_check
from utils.extract_from_json_message import extract_json_from_response, extract_text_before_json
from utils.logging_config import get_logger
from utils.redis_client import (
    get_user_dialogue_history,
    save_user_dialogue_history,
)
from services.openai_service import send_to_gpt
from utils.config import ASSISTANT4_ID

logger = get_logger(name="process_message_barsik")


async def process_user_message_barsik(user_id: str, message: dict, db):
    """
    Обрабатывает сообщение пользователя, поддерживает диалог с GPT и сохраняет результаты опроса.
    """
    try:
        logger.info(f"message_text_from_server: {message}")

        dialogue_history = await get_user_dialogue_history(user_id)
        logger.info(f"dialogue_history: {dialogue_history}")

        # Инициализация диалога
        if message.get("text") == "initial_chat":
            # dialogue_history = [{"role": "user", "content": "Здравствуйте"}]
            # await save_user_dialogue_history(user_id, dialogue_history)

            # gpt_response = await send_to_gpt(dialogue_history, instruction=ASSISTANT4_ID)
            gpt_response_audio = audio_code_first_question

            # text_for_synthesis = extract_text_before_json(gpt_response)
            asyncio.create_task(save_message_to_db(db, user_id, text_code_first_question, False)) # noqa
            # gpt_response_audio = await synthesize_speech(text_for_synthesis)
            dialogue_history.append({"role": "assistant", "content": text_code_first_question})

            asyncio.create_task(save_user_dialogue_history(user_id, dialogue_history)) # noqa

            return {
                "type": "response",
                "status": "success",
                "data": {
                    "audio": gpt_response_audio,
                    "is_last_message": False
                },
            }
        # Обычное сообщение пользователя
        user_text = await process_audio_and_text(message, user_language="ru")
        if user_text:
            asyncio.create_task(save_message_to_db(db, user_id, user_text, True))  # noqa
            logger.info(f"user_text: {user_text}")

            dialogue_history.append({"role": "user", "content": user_text})
            gpt_response = await send_to_gpt(dialogue_history, instruction=ASSISTANT4_ID)

            if gpt_response and "```json" in gpt_response:
                json_data = extract_json_from_response(gpt_response)
                text_for_synthesis = extract_text_before_json(gpt_response)
                asyncio.create_task(save_survey_results(user_id, json_data, db))  # noqa
                gpt_response_audio = await synthesize_speech_with_check(text_for_synthesis, dialogue_history)
                dialogue_history.append({"role": "assistant", "content": text_for_synthesis})
                asyncio.create_task(save_user_dialogue_history(user_id, dialogue_history))  # noqa

                return {
                    "type": "response",
                    "status": "success",
                    "data": {
                        "audio": gpt_response_audio,
                        "is_last_message": True
                    },
                }

            # Если JSON отсутствует
            asyncio.create_task(save_message_to_db(db, user_id, gpt_response, False))  # noqa
            gpt_response_audio = await synthesize_speech_with_check(gpt_response, dialogue_history)
            dialogue_history.append({"role": "assistant", "content": gpt_response})
            asyncio.create_task(save_user_dialogue_history(user_id, dialogue_history))  # noqa

            return {
                "type": "response",
                "status": "success",
                "data": {
                    "audio": gpt_response_audio,
                    "is_last_message": False
                },
            }

        else:
            gpt_response_audio = audio_code_repeat_request
            logger.info(f"gpt_response_audio_11: {gpt_response_audio}")

            return {
                "type": "response",
                "status": "success",
                "data": {
                    "audio": gpt_response_audio,
                    "is_last_message": False
                },
            }

    except Exception as e:
        logger.error(f"Error processing user message: {e}")
        return {
            "type": "response",
            "status": "error",
            "message": "Произошла ошибка при обработке сообщения.",
        }


