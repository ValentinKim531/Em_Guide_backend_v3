import asyncio
import httpx
import websockets
import json
from crud import Postgres
from handlers.process_message import process_user_message
from handlers.process_message_barsik import process_user_message_barsik
from models import User
from utils.logging_config import get_logger
from services.database import async_session
import ftfy

from services.statistics_service import generate_statistics_file
from utils.redis_client import (
    save_registration_status,
    delete_user_dialogue_history,
)

db = Postgres(async_session)


logger = get_logger(name="server")


async def verify_token_with_auth_server(token):
    """
    Проверка токена через внешний сервис аутентификации.
    """
    try:
        url = "https://prod-backoffice.daribar.com/api/v1/users"
        headers = {"Authorization": f"Bearer {token}"}
        logger.info(f"Token: {token}")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                logger.info(f"responseJWT: {response.json()}")
                return response.json()  # Возвращаем данные пользователя
            else:
                logger.error(
                    f"Error: {response.status_code} - {response.text}"
                )
                return None
    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        return None


async def handle_command(action, user_id, database):
    """
    Обрабатывает команды от фронта, включая инициализацию чата и завершение опроса.
    """
    if action == "initial_chat":
        print(f"initial_chat1")
        try:
            message = {"text": "initial_chat"}
            print(f"initial_chat2")
            result = await process_user_message_barsik(user_id, message, database)
            return result
        except Exception as e:
            logger.error(f"Error processing initial chat: {e}")
            return {
                "type": "response",
                "status": "error",
                "message": "Ошибка при обработке команды initial_chat.",
            }
    elif action == "finish_chat":
        try:
            # Удаляем историю диалога после завершения опроса
            logger.info(f"Deleting user dialogue history for user {user_id}")
            await delete_user_dialogue_history(user_id)
            return {
                "type": "response",
                "status": "success",
                "message": "Чат завершён, данные сохранены.",
            }
        except Exception as e:
            logger.error(f"Error finishing chat: {e}")
            return {
                "type": "response",
                "status": "error",
                "message": "Ошибка при завершении чата.",
            }



async def handle_connection(websocket, path):
    """
    Основная логика обработки сообщений по WebSocket.
    """
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                token = data.get("token")
                user_data = None

                # Обработка токена
                if token:
                    try:
                        user_data = await asyncio.create_task(
                            verify_token_with_auth_server(token)
                        )
                    except Exception as token_error:
                        logger.error(f"Error verifying token: {token_error}")
                        response = {
                            "type": "response",
                            "status": "error",
                            "error": "token_verification_error",
                            "message": "Failed to verify authentication token.",
                        }
                        await websocket.send(
                            json.dumps(response, ensure_ascii=False)
                        )
                        continue

                    if not user_data:
                        response = {
                            "type": "response",
                            "status": "error",
                            "error": "invalid_token",
                            "message": "Invalid or expired JWT token. Please re-authenticate.",
                        }
                        await websocket.send(
                            json.dumps(response, ensure_ascii=False)
                        )
                        continue
                else:
                    logger.warning("Token not provided in the request.")
                    response = {
                        "type": "response",
                        "status": "error",
                        "error": "missing_token",
                        "message": "Authentication token is required but was not provided.",
                    }
                    await websocket.send(
                        json.dumps(response, ensure_ascii=False)
                    )
                    continue

                # Проверяем наличие user_data
                if user_data:
                    user_id = user_data["result"]["phone"]
                    action = data.get("action")
                    message_type = data.get("type")
                else:
                    response = {
                        "type": "response",
                        "status": "error",
                        "error": "missing_user_data",
                        "message": "User data not available. Cannot extract user_id.",
                    }
                    await websocket.send(
                        json.dumps(response, ensure_ascii=False)
                    )
                    continue

                if action == "initial_chat" or action == "finish_chat":
                    response = await handle_command(action, user_id, db)
                    await websocket.send(json.dumps(response, ensure_ascii=False))

                # Обработка команды export_stats
                if action == "export_stats":
                    try:
                        response = await handle_command(action, user_id, db)
                        await websocket.send(
                            json.dumps(response, ensure_ascii=False)
                        )
                    except Exception as command_error:
                        logger.error(
                            f"Error handling command 'export_stats': {command_error}"
                        )
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "response",
                                    "status": "error",
                                    "error": "command_error",
                                    "message": "Failed to process the 'export_stats' command.",
                                },
                                ensure_ascii=False,
                            )
                        )
                        continue

                # Обработка сообщений
                if message_type == "message" or (
                    message_type == "command"
                    and action == "all_in_one_message"
                ):
                    try:
                        message_data = data.get("data", {})
                        message_data["action"] = action

                        if "text" in message_data:
                            fixed_text = ftfy.fix_text(message_data["text"])
                            message_data["text"] = fixed_text

                        response = await process_user_message_barsik(
                            user_id, message_data, db
                        )
                        if response:
                            await websocket.send(
                                json.dumps(response, ensure_ascii=False)
                            )
                            audio_data = response.get("data", {}).get("audio")
                            if audio_data:
                                logger.info(f"Response_sent: {audio_data[:100]}")
                            else:
                                logger.info("Response_sent: No audio data available")
                    except Exception as message_error:
                        logger.error(
                            f"Error processing user message: {message_error}"
                        )
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "response",
                                    "status": "error",
                                    "error": "message_processing_error",
                                    "message": "Failed to process the user message.",
                                },
                                ensure_ascii=False,
                            )
                        )
            except websockets.exceptions.ConnectionClosedError as e:
                logger.warning(f"Connection closed unexpectedly: {e}")
                break
            except Exception as message_processing_error:
                logger.error(
                    f"Error processing message: {message_processing_error}"
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "status": "error",
                            "error": "message_error",
                            "message": str(message_processing_error),
                        },
                        ensure_ascii=False,
                    )
                )
    except websockets.exceptions.ConnectionClosedError as e:
        logger.warning(f"WebSocket connection closed unexpectedly: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket handler: {e}")
    finally:
        logger.info("WebSocket connection handler finished.")


async def main():
    try:
        # Увеличиваем время ожидания пинга (интервал и тайм-аут)
        server = await websockets.serve(
            handle_connection,
            "0.0.0.0",
            8085,
            ping_interval=60,  # Интервал между пингами (в секундах)
            ping_timeout=30,  # Время ожидания ответа на пинг (в секундах)
            write_limit=2 ** 20,  # Увеличиваем лимит записи (например, 1 MB)
            max_queue=32,
        )
        print("WebSocket server started on ws://0.0.0.0:8085")
        await server.wait_closed()
    except Exception as e:
        logger.error(f"Error starting WebSocket server: {e}")


if __name__ == "__main__":
    asyncio.run(main())
