"""Leitura da mix e gravação dos stems em WAV 24 bits."""

from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

from vibedj_stems.config import TAXA


def ler_mix(caminho: Path) -> np.ndarray:
    """Devolve a mix em float32, estéreo e 44,1 kHz, com forma (amostras, 2)."""
    try:
        audio, taxa = sf.read(str(caminho), dtype="float32", always_2d=True)
    except Exception:
        audio, taxa = ler_com_miniaudio(caminho)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        audio = audio[:, :2]
    if taxa != TAXA:
        audio = soxr.resample(audio, taxa, TAXA).astype(np.float32)
    return np.ascontiguousarray(audio, dtype=np.float32)


def ler_com_miniaudio(caminho: Path):
    """MP3 e o que o soundfile não abrir. O miniaudio já devolve 44,1 kHz estéreo."""
    import miniaudio

    decodificado = miniaudio.decode_file(
        str(caminho),
        output_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=2,
        sample_rate=TAXA,
    )
    audio = np.frombuffer(decodificado.samples, dtype=np.float32).reshape(-1, decodificado.nchannels).copy()
    return audio, decodificado.sample_rate


def gravar_wav(caminho: Path, audio: np.ndarray) -> None:
    """Grava estéreo PCM 24 bits na taxa do projeto."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(caminho), np.asarray(audio, dtype=np.float32), TAXA, subtype="PCM_24")
