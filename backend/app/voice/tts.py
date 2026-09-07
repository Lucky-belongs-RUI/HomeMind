import asyncio
import base64
import logging
import os
import platform
import subprocess
import tempfile

from app.config import settings

logger = logging.getLogger(__name__)

# Windows SAPI 离线合成脚本：优先选择中文语音，输出 WAV 文件
_SAPI_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:ZHJJ_TTS_TEXT))
$output = $env:ZHJJ_TTS_OUTPUT
$synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synthesizer.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' } | Select-Object -First 1
if ($voice) { $synthesizer.SelectVoice($voice.VoiceInfo.Name) }
$synthesizer.SetOutputToWaveFile($output)
$synthesizer.Speak($text)
$synthesizer.Dispose()
'''


def _sapi_synthesize(text: str, output_path: str) -> str:
    """Windows 本地语音合成（edge-tts 网络不可用时的离线降级）。"""
    if platform.system() != "Windows":
        raise RuntimeError("未检测到可用的 Windows 本地语音")
    script_path = os.path.join(tempfile.gettempdir(), f"zhjj_tts_{os.getpid()}.ps1")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(_SAPI_SCRIPT)
    try:
        env = os.environ.copy()
        env["ZHJJ_TTS_TEXT"] = base64.b64encode(text.encode("utf-8")).decode("ascii")
        env["ZHJJ_TTS_OUTPUT"] = output_path
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if proc.returncode != 0 or not os.path.exists(output_path):
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail or "Windows 本地语音合成失败")
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass
    return output_path


async def text_to_speech(text: str, output_path: str) -> str:
    """文字转语音：优先 edge-tts，失败时降级 Windows 本地语音。"""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, settings.tts_voice)
        await communicate.save(output_path)
        return output_path
    except ImportError:
        logger.warning("未安装 edge-tts，使用 Windows 本地语音")
    except Exception as exc:
        logger.warning("edge-tts 合成失败，降级 Windows 本地语音: %s", exc)
        try:
            os.remove(output_path)
        except OSError:
            pass

    wav_path = output_path.rsplit(".", 1)[0] + ".wav"
    await asyncio.to_thread(_sapi_synthesize, text, wav_path)
    return wav_path