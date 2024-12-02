import asyncio
import base64
import json
import re

import ffmpeg
import tempfile
import httpx
import requests
from utils.logging_config import get_logger
from utils.config import YANDEX_OAUTH_TOKEN, YANDEX_FOLDER_ID
import subprocess
import io

YANDEX_IAM_TOKEN = None

logger = get_logger(name="yandex_service")


async def get_iam_token():
    global YANDEX_IAM_TOKEN
    url = "https://iam.api.cloud.yandex.net/iam/v1/tokens"
    payload = {"yandexPassportOauthToken": YANDEX_OAUTH_TOKEN}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            YANDEX_IAM_TOKEN = response.json()["iamToken"]
            logger.info(f"Received new IAM token: {YANDEX_IAM_TOKEN}")
        except Exception as e:
            logger.error(f"Error getting IAM token: {e}")


async def refresh_iam_token():
    while True:
        try:
            await asyncio.sleep(6 * 3600)  # Ждём 6 часов
            await get_iam_token()  # Асинхронно обновляем токен
            logger.info("IAM token refreshed")
        except Exception as e:
            logger.error(f"Error refreshing IAM token: {e}")


def recognize_speech(audio_content, lang="ru-RU"):
    try:
        if not YANDEX_IAM_TOKEN:
            get_iam_token()
        url = f"https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?folderId={YANDEX_FOLDER_ID}&lang={lang}"
        headers = {"Authorization": f"Bearer {YANDEX_IAM_TOKEN}"}

        response = requests.post(url, headers=headers, data=audio_content)

        if response.status_code == 200:
            result = response.json().get("result")
            if not result:
                logger.info(
                    "Recognition result is empty. Asking user to repeat the question."
                )
                return "Пожалуйста, повторите, сообщив, что не расслышали мой ответ"
            return result
        else:
            error_message = f"Failed to recognize speech, status code: {response.status_code}, response text: {response.text}"
            logger.error(error_message)
            raise Exception(error_message)
    except Exception as e:
        logger.error(f"Error in recognize_speech: {e}")
        return None


def convert_mp3_to_aac(input_mp3, output_aac):
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_mp3, "-c:a", "aac", output_aac],
            check=False,
        )
        print(f"Conversion successful: {output_aac}")
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr.decode('utf8')}")


def clean_text_for_synthesis(text):
    """
    Удаляет лишние пробелы и переносы строк, оставляя только один пробел между словами.
    """
    return re.sub(r'\s+', ' ', text).strip()


async def synthesize_speech(
    text
):
    voice = "marina"
    pitch_shift = 400
    speed = 1.5
    emotion = "friendly"
    volume = 0.9
    lang_code = "ru-RU"

    try:
        text = clean_text_for_synthesis(text)
        logger.info(f"Cleaned text for synthesis: {repr(text)}")
        logger.info(f"Text length for synthesis: {len(text)}")

        url = "https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis"
        headers = {
            "Authorization": f"Bearer {YANDEX_IAM_TOKEN}",
            "x-folder-id": YANDEX_FOLDER_ID,
            "Content-Type": "application/json; charset=utf-8",
        }

        data = {
            "text": text,
            "hints": [
                {"speed": speed},  # Скорость речи
                {"voice": voice},  # Выбор голоса
                {"role": emotion},  # Эмоция речи
                {"pitchShift": pitch_shift},  # Изменение тембра
                {"volume": volume},  # Громкость речи
            ],
            "outputAudioSpec": {
                "containerAudio": {
                    "containerAudioType": "MP3"
                }  # Используем MP3
            },
        }

        # Преобразование данных в JSON
        json_data = json.dumps(data, ensure_ascii=False)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                content=json_data,  # Используем content для передачи JSON
            )

        if response.status_code == 200:
            response_json = response.json()

            # Извлечение аудиоданных
            audio_data = response_json.get("result", {}).get("audioChunk", {}).get("data")
            if audio_data:
                audio_bytes = base64.b64decode(audio_data)

                # Сохранение MP3
                temp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                with open(temp_mp3.name, "wb") as audio_file:
                    audio_file.write(audio_bytes)
                logger.info(f"Audio saved as MP3: {temp_mp3.name}")

                # Конвертация в AAC
                temp_aac = tempfile.NamedTemporaryFile(delete=False, suffix=".aac")
                ffmpeg_command = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_mp3.name,
                    "-c:a",
                    "aac",
                    temp_aac.name,
                ]
                subprocess.run(ffmpeg_command, check=True)
                logger.info(f"Successfully converted MP3 to AAC: {temp_aac.name}")

                # Чтение и сохранение в локальной директории
                save_path = "saved_audio.aac"
                with open(temp_aac.name, "rb") as f:
                    aac_data = f.read()
                with open(save_path, "wb") as save_file:
                    save_file.write(aac_data)
                logger.info(f"AAC audio saved locally at {save_path}")

                encoded_audio = base64.b64encode(aac_data).decode("utf-8")
                return encoded_audio

            else:
                logger.error("Audio data not found in the response")
        else:
            logger.error(
                f"Failed to synthesize speech, status code: {response.status_code}, response text: {response.text}"
            )
            raise Exception(f"Failed with status code {response.status_code}")

    except Exception as e:
        logger.error(f"Exception in synthesize_speech_httpx: {e}")
        return None


def translate_text(text, source_lang="ru", target_lang="kk"):
    url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
    headers = {
        "Authorization": f"Bearer {YANDEX_IAM_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "folder_id": YANDEX_FOLDER_ID,
        "texts": [text],
        "targetLanguageCode": target_lang,
        "sourceLanguageCode": source_lang,
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        translations = response.json().get("translations", [])
        if translations:
            return translations[0]["text"]
        else:
            logger.error("Translation not found in response")
            return "Перевод не найден."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during translation request: {e}")
        return "Ошибка при запросе перевода."
    except Exception as e:
        logger.error(f"Unexpected error during translation: {e}")
        return "Произошла неожиданная ошибка."
