"""Four-view multiple-instance regression with explicit path masks."""

import torch
from torch import nn


def pool(scores, mask, temperature=None):
    if not bool(mask.any(dim=-1).all()):
        raise ValueError("Empty path bag")
    masked = scores.masked_fill(~mask, -torch.inf)
    if temperature is None:
        # torch.max chooses the first maximum; fixed path ordering pairs tie behavior.
        return masked.max(dim=-1).values
    if temperature <= 0:
        raise ValueError("Temperature must be positive")
    return temperature * (
        torch.logsumexp(masked / temperature, dim=-1) - mask.sum(dim=-1).log()
    )


class PathModel(nn.Module):
    def __init__(self, inputs, hidden, learned_mix=False):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(inputs, hidden[0]),
            nn.ReLU(),
            nn.Linear(hidden[0], hidden[1]),
            nn.ReLU(),
            nn.Linear(hidden[1], 1),
            nn.Softplus(),
        )
        if learned_mix:
            self.logits = nn.Parameter(torch.zeros(4))
        else:
            self.register_buffer("logits", torch.zeros(4))

    def forward(self, x, mask, temperature=None, return_views=False):
        scores = self.mlp(x).squeeze(-1)
        views = pool(scores, mask, temperature)
        prediction = (views * self.logits.softmax(dim=0)).sum(dim=-1)
        return (prediction, views) if return_views else prediction


def temperature(config, model, epoch):
    if model == "N0" or epoch > config["smooth_epochs"]:
        return None
    return config["temperature_start"] * (
        config["temperature_end"] / config["temperature_start"]
    ) ** ((epoch - 1) / (config["smooth_epochs"] - 1))


def epoch_order(n, seed, epoch):
    generator = torch.Generator().manual_seed(seed * 1000003 + epoch)
    return torch.randperm(n, generator=generator)


def optimizer_for(model, config):
    groups = [
        {"params": model.mlp.parameters(), "weight_decay": config["weight_decay"]}
    ]
    if isinstance(model.logits, nn.Parameter):
        groups.append({"params": [model.logits], "weight_decay": 0.0})
    return torch.optim.AdamW(groups, lr=config["learning_rate"])


def training_epoch(model, optimizer, x, mask, y, seed, epoch, config, model_name):
    model.train()
    order = epoch_order(len(y), seed, epoch)
    total = 0.0
    gradients, batch_rows = [], []
    for idx in order.split(config["batch_size"]):
        idx = idx.to(x.device)
        optimizer.zero_grad(set_to_none=True)
        prediction = model(x[idx], mask[idx], temperature(config, model_name, epoch))
        loss = (prediction - y[idx]).abs().mean()
        if not bool(torch.isfinite(loss)):
            raise ValueError("Nonfinite training loss")
        loss.backward()
        gradient = nn.utils.clip_grad_norm_(
            model.parameters(), config["gradient_clip"], error_if_nonfinite=True
        )
        optimizer.step()
        total += float(loss.detach()) * len(idx)
        gradients.append(float(gradient))
        batch_rows.append(
            {
                "batch": len(batch_rows),
                "count": len(idx),
                "loss_scaled": float(loss.detach()),
                "gradient_norm_before_clip": float(gradient),
            }
        )
    return total / len(y), gradients, batch_rows


@torch.no_grad()
def predict(model, x, mask, temperature=None):
    model.eval()
    out = []
    for start in range(0, len(x), 128):
        out.append(
            model(x[start : start + 128], mask[start : start + 128], temperature).cpu()
        )
    return torch.cat(out).numpy()
