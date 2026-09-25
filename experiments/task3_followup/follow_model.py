"""Ablate other views while retaining identical MLP parameters and inputs."""

import torch
from neural import PathModel


class SOGModel(PathModel):
    def __init__(self, inputs, hidden, learned_mix=False):
        if learned_mix:
            raise ValueError("SOG-only model has no learned representation mixing")
        super().__init__(inputs, hidden, False)
        self.logits = torch.zeros(1)  # A fixed weight of one; no additional parameters.

    def forward(self, x, mask, temperature=None, return_views=False):
        if x.shape[1] != 1 or mask.shape[1] != 1:
            raise ValueError("SOG-only forward requires exactly one view")
        return super().forward(x, mask, temperature, return_views)
