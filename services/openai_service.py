import json
import anthropic
import asyncio
from utils.config import ANTHROPIC_API_KEY
import time
from openai import AsyncOpenAI
from utils.config import OPENAI_API_KEY
from utils.logging_config import get_logger

logger = get_logger(name="openai_service")


client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def send_to_gpt(dialogue_history, instruction):
    """
    Отправляет историю диалога и инструкцию в GPT.
    """
    try:
        messages = [{"role": "system", "content": instruction}] + dialogue_history
        logger.info(f"Sending to GPT: {messages}")

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=10000,
            temperature=0.7,
        )
        gpt_reply = response.choices[0].message.content
        logger.info(f"GPT Response: {gpt_reply}")
        return gpt_reply
    except Exception as e:
        logger.error(f"Error in send_to_gpt: {e}")
        return "Пожалуйста, повторите ваш ответ"

