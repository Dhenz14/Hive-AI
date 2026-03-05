"""Speech and audio ML — ASR, TTS, audio classification, voice cloning."""

PAIRS = [
    (
        "ai/speech-recognition",
        "Show speech recognition patterns: Whisper-style ASR pipeline, audio preprocessing (mel spectrograms), CTC decoding, and streaming transcription.",
        '''Speech recognition (ASR) pipeline:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from dataclasses import dataclass


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    n_mels: int = 80
    n_fft: int = 400
    hop_length: int = 160
    chunk_length: int = 30  # seconds
    max_tokens: int = 448


class AudioPreprocessor:
    """Convert raw audio to mel spectrograms (Whisper-style)."""

    def __init__(self, config: AudioConfig = AudioConfig()):
        self.config = config

    def log_mel_spectrogram(self, audio: np.ndarray) -> torch.Tensor:
        """Compute log-mel spectrogram from raw audio waveform."""
        # Pad or trim to chunk length
        target_length = self.config.sample_rate * self.config.chunk_length
        if len(audio) < target_length:
            audio = np.pad(audio, (0, target_length - len(audio)))
        else:
            audio = audio[:target_length]

        # STFT
        audio_tensor = torch.FloatTensor(audio)
        stft = torch.stft(
            audio_tensor, n_fft=self.config.n_fft,
            hop_length=self.config.hop_length,
            window=torch.hann_window(self.config.n_fft),
            return_complex=True,
        )
        magnitudes = stft.abs().pow(2)

        # Mel filterbank
        mel_filters = self._mel_filterbank()
        mel_spec = mel_filters @ magnitudes

        # Log scale with floor
        log_spec = torch.clamp(mel_spec, min=1e-10).log10()
        log_spec = torch.maximum(log_spec, log_spec.max() - 8.0)
        log_spec = (log_spec + 4.0) / 4.0  # Normalize

        return log_spec

    def _mel_filterbank(self) -> torch.Tensor:
        """Create mel-frequency filterbank matrix."""
        n_freqs = self.config.n_fft // 2 + 1
        mel_low = self._hz_to_mel(0)
        mel_high = self._hz_to_mel(self.config.sample_rate / 2)

        mel_points = torch.linspace(mel_low, mel_high, self.config.n_mels + 2)
        hz_points = self._mel_to_hz(mel_points)
        bin_points = (hz_points * self.config.n_fft / self.config.sample_rate).long()

        filterbank = torch.zeros(self.config.n_mels, n_freqs)
        for i in range(self.config.n_mels):
            left, center, right = bin_points[i], bin_points[i+1], bin_points[i+2]
            for j in range(left, center):
                filterbank[i, j] = (j - left) / max(center - left, 1)
            for j in range(center, right):
                filterbank[i, j] = (right - j) / max(right - center, 1)

        return filterbank

    @staticmethod
    def _hz_to_mel(hz):
        return 2595 * np.log10(1 + hz / 700)

    @staticmethod
    def _mel_to_hz(mel):
        return 700 * (10 ** (mel / 2595) - 1)


class WhisperEncoder(nn.Module):
    """Whisper-style audio encoder: conv stem + transformer."""

    def __init__(self, n_mels: int = 80, d_model: int = 512, n_heads: int = 8, n_layers: int = 6):
        super().__init__()
        # Conv stem: downsample mel spectrogram
        self.conv1 = nn.Conv1d(n_mels, d_model, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(d_model, d_model, kernel_size=3, stride=2, padding=1)
        self.pos_embed = nn.Embedding(1500, d_model)

        # Transformer encoder
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads,
            dim_feedforward=d_model * 4, dropout=0.1,
            batch_first=True, norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.ln = nn.LayerNorm(d_model)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """mel: [batch, n_mels, time] -> [batch, time//2, d_model]"""
        x = F.gelu(self.conv1(mel))
        x = F.gelu(self.conv2(x))
        x = x.transpose(1, 2)  # [B, T, D]

        positions = torch.arange(x.shape[1], device=x.device)
        x = x + self.pos_embed(positions)
        x = self.transformer(x)
        return self.ln(x)


class CTCDecoder:
    """CTC greedy decoder for speech recognition."""

    def __init__(self, vocab: list[str], blank_idx: int = 0):
        self.vocab = vocab
        self.blank_idx = blank_idx

    def decode(self, logits: torch.Tensor) -> str:
        """Greedy CTC decoding: collapse repeats and remove blanks."""
        predictions = logits.argmax(dim=-1)  # [time]
        decoded = []
        prev = self.blank_idx

        for t in range(predictions.shape[0]):
            token = predictions[t].item()
            if token != self.blank_idx and token != prev:
                decoded.append(self.vocab[token])
            prev = token

        return " ".join(decoded)
```

Key patterns:
1. **Log-mel spectrogram** — standard audio representation; 80 mel bins, log-scaled, normalized
2. **Conv stem** — downsample time dimension 2x before transformer; reduces compute
3. **CTC decoding** — collapse repeated tokens and remove blanks; no autoregressive decoder needed
4. **Chunk processing** — fixed 30s chunks; pad shorter audio, split longer recordings
5. **Positional embedding** — sinusoidal or learned positions over the time dimension'''
    ),
    (
        "ai/text-to-speech",
        "Show text-to-speech patterns: mel spectrogram generation, vocoder (HiFi-GAN), prosody control, and streaming TTS.",
        '''Text-to-speech pipeline:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np


class TextEncoder(nn.Module):
    """Encode phonemes/text to hidden representations."""

    def __init__(self, vocab_size: int, d_model: int = 256,
                 n_layers: int = 4, n_heads: int = 4):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, d_model)
        self.pos_embed = nn.Embedding(512, d_model)
        layer = nn.TransformerEncoderLayer(
            d_model, n_heads, d_model * 4, dropout=0.1,
            batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, n_layers)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        positions = torch.arange(tokens.shape[1], device=tokens.device)
        x = self.embed(tokens) + self.pos_embed(positions)
        return self.encoder(x)


class DurationPredictor(nn.Module):
    """Predict duration (in mel frames) for each phoneme.

    Non-autoregressive TTS uses duration prediction to align
    text and mel spectrogram without attention.
    """

    def __init__(self, d_model: int = 256):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv1d(d_model, d_model, 3, padding=1),
            nn.ReLU(), nn.LayerNorm(d_model),
            nn.Conv1d(d_model, d_model, 3, padding=1),
            nn.ReLU(), nn.LayerNorm(d_model),
            nn.Linear(d_model, 1),
        )

    def forward(self, encoder_output: torch.Tensor) -> torch.Tensor:
        """Predict log-duration for each token."""
        x = encoder_output.transpose(1, 2)
        x = self.layers[0](x)
        x = self.layers[1](x)
        x = x.transpose(1, 2)
        x = self.layers[2](x)
        x = x.transpose(1, 2)
        x = self.layers[3](x)
        x = self.layers[4](x)
        x = x.transpose(1, 2)
        x = self.layers[5](x)
        return self.layers[6](x).squeeze(-1)  # [B, T_text]


def length_regulate(encoder_output: torch.Tensor, durations: torch.Tensor) -> torch.Tensor:
    """Expand encoder output by predicted durations.

    Each phoneme embedding is repeated for its predicted duration.
    e.g., durations=[2,3,1] expands [a,b,c] -> [a,a,b,b,b,c]
    """
    durations = durations.long().clamp(min=1)
    expanded = []
    for i in range(encoder_output.shape[0]):
        expanded.append(
            encoder_output[i].repeat_interleave(durations[i], dim=0)
        )
    return torch.nn.utils.rnn.pad_sequence(expanded, batch_first=True)


class MelDecoder(nn.Module):
    """Decode expanded representations to mel spectrogram."""

    def __init__(self, d_model: int = 256, n_mels: int = 80, n_layers: int = 4):
        super().__init__()
        layer = nn.TransformerEncoderLayer(
            d_model, nhead=4, dim_feedforward=d_model * 4,
            batch_first=True, norm_first=True,
        )
        self.decoder = nn.TransformerEncoder(layer, n_layers)
        self.mel_proj = nn.Linear(d_model, n_mels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.decoder(x)
        return self.mel_proj(x)  # [B, T_mel, n_mels]


class HiFiGANGenerator(nn.Module):
    """HiFi-GAN vocoder: convert mel spectrogram to waveform.

    Uses transposed convolutions for upsampling and multi-receptive
    field fusion (MRF) blocks for quality.
    """

    def __init__(self, n_mels: int = 80, upsample_rates: list[int] = None):
        super().__init__()
        upsample_rates = upsample_rates or [8, 8, 2, 2]
        channels = 512

        self.conv_pre = nn.Conv1d(n_mels, channels, 7, padding=3)

        self.ups = nn.ModuleList()
        for rate in upsample_rates:
            self.ups.append(nn.Sequential(
                nn.LeakyReLU(0.1),
                nn.ConvTranspose1d(
                    channels, channels // 2,
                    kernel_size=rate * 2, stride=rate,
                    padding=rate // 2,
                ),
            ))
            channels //= 2

        self.conv_post = nn.Conv1d(channels, 1, 7, padding=3)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """mel: [B, n_mels, T] -> waveform: [B, 1, T * prod(upsample_rates)]"""
        x = self.conv_pre(mel)
        for up in self.ups:
            x = up(x)
        x = torch.tanh(self.conv_post(F.leaky_relu(x, 0.1)))
        return x
```

TTS pipeline comparison:

| Component | Non-autoregressive | Autoregressive |
|-----------|-------------------|----------------|
| **Speed** | Real-time+ (parallel) | Slower (sequential) |
| **Quality** | Good (with vocoder) | Excellent |
| **Prosody** | Needs explicit modeling | Learned from data |
| **Streaming** | Easy (chunk-based) | Hard (sequential) |

Key patterns:
1. **Duration prediction** — predict mel frames per phoneme; enables parallel synthesis
2. **Length regulation** — repeat encoder outputs by duration; aligns text and mel dimensions
3. **HiFi-GAN vocoder** — transposed conv upsampling from mel to waveform; fast and high-quality
4. **Non-autoregressive** — parallel generation is 10-100x faster than autoregressive
5. **Mel spectrogram** — intermediate representation between text and audio; compact and invertible'''
    ),
    (
        "ai/audio-classification",
        "Show audio classification and sound event detection: audio feature extraction, CNN/transformer classifiers, and multi-label tagging.",
        '''Audio classification and sound event detection:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchaudio
import torchaudio.transforms as T


class AudioFeatureExtractor:
    """Extract features from raw audio for classification."""

    def __init__(self, sample_rate: int = 16000, n_mels: int = 128):
        self.sample_rate = sample_rate
        self.mel_transform = T.MelSpectrogram(
            sample_rate=sample_rate,
            n_fft=1024,
            hop_length=512,
            n_mels=n_mels,
        )
        self.amplitude_to_db = T.AmplitudeToDB()

    def __call__(self, waveform: torch.Tensor) -> torch.Tensor:
        """waveform: [channels, time] -> mel_db: [1, n_mels, time_frames]"""
        # Mono conversion
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Resample if needed
        mel = self.mel_transform(waveform)
        mel_db = self.amplitude_to_db(mel)
        return mel_db


class AudioClassifier(nn.Module):
    """CNN-based audio classifier (AudioSet-style).

    Treats mel spectrogram as a single-channel image.
    """

    def __init__(self, n_classes: int, n_mels: int = 128):
        super().__init__()
        self.features = nn.Sequential(
            # Block 1
            nn.Conv2d(1, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.Conv2d(64, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d(2),

            # Block 2
            nn.Conv2d(64, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.Conv2d(128, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d(2),

            # Block 3
            nn.Conv2d(128, 256, 3, padding=1), nn.BatchNorm2d(256), nn.ReLU(),
            nn.Conv2d(256, 256, 3, padding=1), nn.BatchNorm2d(256), nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )

        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, n_classes),
        )

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """mel: [B, 1, n_mels, time] -> logits: [B, n_classes]"""
        features = self.features(mel)
        return self.classifier(features)


class SoundEventDetector(nn.Module):
    """Multi-label sound event detection with temporal resolution.

    Outputs per-frame predictions for overlapping sound events.
    """

    def __init__(self, n_classes: int, n_mels: int = 128, d_model: int = 256):
        super().__init__()
        # CNN feature extractor
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d((2, 1)),
            nn.Conv2d(64, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d((2, 1)),
            nn.Conv2d(128, d_model, 3, padding=1), nn.BatchNorm2d(d_model), nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, None)),  # Pool frequency, keep time
        )

        # Temporal modeling
        layer = nn.TransformerEncoderLayer(
            d_model, nhead=4, dim_feedforward=d_model * 2,
            batch_first=True, dropout=0.1,
        )
        self.temporal = nn.TransformerEncoder(layer, num_layers=2)
        self.head = nn.Linear(d_model, n_classes)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """mel: [B, 1, n_mels, T] -> [B, T', n_classes] (per-frame logits)"""
        x = self.cnn(mel)  # [B, d_model, 1, T']
        x = x.squeeze(2).transpose(1, 2)  # [B, T', d_model]
        x = self.temporal(x)
        return self.head(x)  # Multi-label: use sigmoid, not softmax

    def predict(self, mel: torch.Tensor, threshold: float = 0.5) -> torch.Tensor:
        logits = self.forward(mel)
        return (torch.sigmoid(logits) > threshold).float()
```

Key patterns:
1. **Mel spectrogram as image** — treat [n_mels, time] as single-channel image; use 2D CNNs
2. **Multi-label detection** — sigmoid (not softmax) for overlapping sound events
3. **Temporal resolution** — per-frame predictions for sound event detection; pool frequency, keep time
4. **AmplitudeToDB** — log-scale mel spectrogram in decibels; better for neural networks
5. **Adaptive pooling** — handle variable-length audio with AdaptiveAvgPool2d'''
    ),
    (
        "ai/voice-embeddings",
        "Show voice/speaker embeddings: speaker verification, speaker diarization, and voice similarity with embedding models.",
        '''Speaker embeddings and verification:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class SpeakerEncoder(nn.Module):
    """Speaker embedding network (d-vector / x-vector style).

    Maps variable-length audio to fixed-size speaker embedding.
    Used for verification, diarization, and voice cloning.
    """

    def __init__(self, n_mels: int = 80, embed_dim: int = 256, hidden: int = 768):
        super().__init__()
        # Frame-level feature extraction
        self.frame_layers = nn.Sequential(
            nn.Conv1d(n_mels, hidden, 5, padding=2), nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.Conv1d(hidden, hidden, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(hidden),
            nn.Conv1d(hidden, hidden, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(hidden),
        )

        # Statistics pooling: concat mean and std over time
        self.segment_layer = nn.Sequential(
            nn.Linear(hidden * 2, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, embed_dim),
        )

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """mel: [B, n_mels, T] -> embedding: [B, embed_dim]"""
        frame_features = self.frame_layers(mel)  # [B, hidden, T]

        # Statistics pooling
        mean = frame_features.mean(dim=2)
        std = frame_features.std(dim=2)
        stats = torch.cat([mean, std], dim=1)  # [B, hidden*2]

        embedding = self.segment_layer(stats)
        return F.normalize(embedding, dim=1)  # L2 normalized


class SpeakerVerifier:
    """Speaker verification: is this the same person?"""

    def __init__(self, encoder: SpeakerEncoder, threshold: float = 0.7):
        self.encoder = encoder
        self.threshold = threshold

    @torch.no_grad()
    def verify(self, mel_a: torch.Tensor, mel_b: torch.Tensor) -> dict:
        """Compare two audio segments for speaker identity."""
        embed_a = self.encoder(mel_a)
        embed_b = self.encoder(mel_b)

        similarity = F.cosine_similarity(embed_a, embed_b).item()
        return {
            "same_speaker": similarity > self.threshold,
            "similarity": similarity,
            "threshold": self.threshold,
        }

    @torch.no_grad()
    def enroll(self, mel_segments: list[torch.Tensor]) -> torch.Tensor:
        """Create speaker profile from multiple segments (average embedding)."""
        embeddings = [self.encoder(mel) for mel in mel_segments]
        mean_embed = torch.stack(embeddings).mean(dim=0)
        return F.normalize(mean_embed, dim=1)


class SpeakerDiarizer:
    """Speaker diarization: who spoke when?

    Process: segment audio -> extract embeddings -> cluster -> assign labels.
    """

    def __init__(self, encoder: SpeakerEncoder, segment_duration: float = 1.5,
                 hop_duration: float = 0.75):
        self.encoder = encoder
        self.segment_duration = segment_duration
        self.hop_duration = hop_duration

    @torch.no_grad()
    def diarize(self, mel: torch.Tensor, n_speakers: int = None) -> list[dict]:
        """mel: [1, n_mels, T] -> list of {speaker, start, end}"""
        # Segment audio into overlapping windows
        hop_frames = int(self.hop_duration * 100)  # ~100 frames/sec
        seg_frames = int(self.segment_duration * 100)

        embeddings = []
        timestamps = []
        T = mel.shape[2]

        for start in range(0, T - seg_frames, hop_frames):
            segment = mel[:, :, start:start + seg_frames]
            embed = self.encoder(segment)
            embeddings.append(embed.squeeze(0))
            timestamps.append((start / 100, (start + seg_frames) / 100))

        if not embeddings:
            return []

        # Cluster embeddings (spectral clustering or agglomerative)
        embed_matrix = torch.stack(embeddings).cpu().numpy()
        labels = self._cluster(embed_matrix, n_speakers)

        # Convert to segments
        segments = []
        for (start, end), label in zip(timestamps, labels):
            if segments and segments[-1]["speaker"] == label:
                segments[-1]["end"] = end  # Merge consecutive same-speaker segments
            else:
                segments.append({"speaker": int(label), "start": start, "end": end})

        return segments

    def _cluster(self, embeddings, n_speakers=None):
        """Cluster speaker embeddings."""
        from sklearn.cluster import AgglomerativeClustering

        if n_speakers is None:
            n_speakers = 2  # Default assumption
        clustering = AgglomerativeClustering(
            n_clusters=n_speakers, metric="cosine", linkage="average",
        )
        return clustering.fit_predict(embeddings)
```

Key patterns:
1. **Statistics pooling** — concatenate mean+std over time; maps variable-length to fixed-size
2. **L2 normalization** — normalize embeddings to unit sphere; cosine similarity = dot product
3. **Speaker verification** — cosine similarity > threshold → same speaker
4. **Diarization pipeline** — segment → embed → cluster → assign speaker labels
5. **Enrollment** — average multiple embeddings for robust speaker profile'''
    ),
]
