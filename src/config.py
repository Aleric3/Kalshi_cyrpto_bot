from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    max_position_size: float = 1.0
    divergence_threshold: float = 0.05
    fill_model_mode: str = "realistic"
    default_slippage_bps: float = 50.0
    competition_miss_prob: float = 0.50
