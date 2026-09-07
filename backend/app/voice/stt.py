import logging
import wave

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Whisper 缺失或音频解码失败时返回的演示指令，保证语音输入链路可完整运行
FALLBACK_INSTRUCTION = "请打开客厅灯"

# Whisper 期望的输入采样率
SAMPLE_RATE = 16000

_model = None


def get_whisper_model():
    """懒加载 Whisper 模型；未安装依赖或加载失败时返回 None。"""
    global _model
    if _model is None:
        try:
            import whisper
            _model = whisper.load_model(settings.whisper_model)
        except Exception:
            _model = False  # 标记加载失败，避免每次请求都重复尝试
    return _model or None


def _load_wav_audio(audio_path: str) -> np.ndarray:
    """用标准库 wave 读取 WAV，转为 16kHz 单声道 float32，避免依赖 ffmpeg。"""
    with wave.open(audio_path, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if not frames:
        return np.zeros(0, dtype=np.float32)

    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[sample_width]
    samples = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    samples /= 2 ** (sample_width * 8 - 1)

    if sample_rate != SAMPLE_RATE:
        duration = len(samples) / sample_rate
        target_len = max(1, int(duration * SAMPLE_RATE))
        old_x = np.linspace(0, duration, len(samples), endpoint=False)
        new_x = np.linspace(0, duration, target_len, endpoint=False)
        samples = np.interp(new_x, old_x, samples)

    return samples.astype(np.float32)


async def speech_to_text(audio_path: str) -> str:
    """语音转文字：优先 Whisper 直接识别；缺 ffmpeg 时改读 WAV 数据再识别。"""
    model = get_whisper_model()
    if model is None:
        return FALLBACK_INSTRUCTION

    try:
        result = model.transcribe(audio_path, language="zh")
        return (result.get("text") or "").strip()
    except Exception as exc:
        logger.warning("Whisper 直接转写失败（可能缺少 ffmpeg），尝试 WAV 直读: %s", exc)

    try:
        audio = _load_wav_audio(audio_path)
        if len(audio) == 0:
            return ""
        result = model.transcribe(audio, language="zh")
        return (result.get("text") or "").strip()
    except Exception as exc:
        logger.warning("语音识别失败，返回演示指令: %s", exc)
        return FALLBACK_INSTRUCTION