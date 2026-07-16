from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn
import torch.nn.functional as F


class ConvLSTMCell(nn.Module):
    def __init__(self, input_channels: int, hidden_channels: int, kernel_size: int = 3) -> None:
        super().__init__()
        padding = kernel_size // 2
        self.hidden_channels = hidden_channels
        self.gates = nn.Conv2d(
            input_channels + hidden_channels,
            4 * hidden_channels,
            kernel_size=kernel_size,
            padding=padding,
        )

    def forward(self, x: Tensor, state: tuple[Tensor, Tensor] | None) -> tuple[Tensor, Tensor]:
        if state is None:
            batch, _, height, width = x.shape
            h_prev = x.new_zeros(batch, self.hidden_channels, height, width)
            c_prev = x.new_zeros(batch, self.hidden_channels, height, width)
        else:
            h_prev, c_prev = state

        combined = torch.cat([x, h_prev], dim=1)
        i, f, o, g = torch.chunk(self.gates(combined), 4, dim=1)
        i = torch.sigmoid(i)
        f = torch.sigmoid(f)
        o = torch.sigmoid(o)
        g = torch.tanh(g)
        c = f * c_prev + i * g
        h = o * torch.tanh(c)
        return h, c


class ChannelAttention(nn.Module):
    def __init__(self, channels: int, reduction: int = 8) -> None:
        super().__init__()
        hidden = max(channels // reduction, 4)
        self.mlp = nn.Sequential(
            nn.Conv2d(channels, hidden, kernel_size=1),
            nn.Mish(),
            nn.Conv2d(hidden, channels, kernel_size=1),
        )

    def forward(self, x: Tensor) -> Tensor:
        avg_pool = F.adaptive_avg_pool2d(x, output_size=1)
        max_pool = F.adaptive_max_pool2d(x, output_size=1)
        attn = torch.sigmoid(self.mlp(avg_pool) + self.mlp(max_pool))
        return x * attn


class SpatialAttention(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(2, 1, kernel_size=7, padding=3)

    def forward(self, x: Tensor) -> Tensor:
        avg_pool = torch.mean(x, dim=1, keepdim=True)
        max_pool, _ = torch.max(x, dim=1, keepdim=True)
        attn = torch.sigmoid(self.conv(torch.cat([avg_pool, max_pool], dim=1)))
        return x * attn


class CBAM(nn.Module):
    def __init__(self, channels: int, reduction: int = 8) -> None:
        super().__init__()
        self.channel = ChannelAttention(channels, reduction=reduction)
        self.spatial = SpatialAttention()

    def forward(self, x: Tensor) -> Tensor:
        return self.spatial(self.channel(x))


class StaticEncoder(nn.Module):
    def __init__(self, in_channels: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.GroupNorm(8, 32),
            nn.Mish(),
            nn.Conv2d(32, 48, kernel_size=3, padding=1),
            nn.GroupNorm(8, 48),
            nn.Mish(),
            nn.Conv2d(48, 32, kernel_size=3, padding=1),
            nn.Mish(),
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


class FeatureFiLM(nn.Module):
    def __init__(self, cond_dim: int, channels: int) -> None:
        super().__init__()
        hidden = max(16, channels // 2)
        self.net = nn.Sequential(
            nn.Linear(cond_dim, hidden),
            nn.SiLU(),
            nn.Linear(hidden, 2 * channels),
        )

    def forward(self, x: Tensor, cond: Tensor) -> Tensor:
        gamma, beta = torch.chunk(self.net(cond), 2, dim=1)
        gamma = gamma[:, :, None, None]
        beta = beta[:, :, None, None]
        return x * (1.0 + gamma) + beta


class HNPSurrogateModel(nn.Module):
    def __init__(
        self,
        variant: str = "model_b",
        *,
        use_film: bool = False,
        split_heads: bool = False,
        use_stage_progress_features: bool = False,
        use_transition_features: bool = False,
        use_transition_refine: bool = False,
        output_contract: str = "legacy",
        use_stage_experts: bool = False,
        stage_expert_scale: float = 0.1,
        use_transition_gas_fraction: bool = False,
        transition_gas_min_count_ratio: float = 0.0,
    ) -> None:
        super().__init__()
        if variant not in {"model_a", "model_b"}:
            raise ValueError(f"Unsupported model variant: {variant}")
        if output_contract not in {"legacy", "production_v2"}:
            raise ValueError(f"Unsupported output_contract: {output_contract}")
        if output_contract == "production_v2" and variant != "model_b":
            raise ValueError("production_v2 output_contract is only supported for model_b.")
        if use_stage_experts and variant != "model_b":
            raise ValueError("Stage experts are only supported for model_b.")
        self.variant = variant
        self.output_contract = output_contract
        self.use_production_v2 = output_contract == "production_v2"
        self.use_static = variant == "model_b"
        self.use_cbam = variant == "model_b"
        self.use_film = use_film and self.use_static
        self.split_heads = split_heads and self.use_static
        self.use_stage_progress_features = use_stage_progress_features and self.use_static
        self.use_transition_features = use_transition_features and self.use_static
        self.use_transition_refine = use_transition_refine and self.use_static
        self.use_stage_experts = use_stage_experts and self.use_static
        self.stage_expert_scale = float(stage_expert_scale)
        self.use_transition_gas_fraction = bool(use_transition_gas_fraction) and self.use_production_v2 and self.use_static
        self.transition_gas_min_count_ratio = float(transition_gas_min_count_ratio)
        base_dynamic_channels = 13 if self.use_stage_progress_features else (11 if self.use_static else 2)
        transition_channels = 7 if self.use_transition_features else 0
        dynamic_channels = base_dynamic_channels + transition_channels
        static_channels = 12 if self.use_static else 0
        input_channels = dynamic_channels + (32 if self.use_static else 0)

        self.static_encoder = StaticEncoder(static_channels) if self.use_static else None
        self.conv_lstm_1 = ConvLSTMCell(input_channels=input_channels, hidden_channels=48, kernel_size=3)
        self.downsample = nn.Conv2d(48, 64, kernel_size=3, stride=2, padding=1)
        self.conv_lstm_2 = ConvLSTMCell(input_channels=64, hidden_channels=96, kernel_size=3)
        self.film_1 = FeatureFiLM(cond_dim=7, channels=48) if self.use_film else None
        self.film_2 = FeatureFiLM(cond_dim=7, channels=96) if self.use_film else None
        self.bottleneck = CBAM(96, reduction=8) if self.use_cbam else nn.Identity()
        self.up = nn.ConvTranspose2d(96, 48, kernel_size=2, stride=2)
        self.decoder = nn.Sequential(
            nn.Conv2d(96, 48, kernel_size=3, padding=1),
            nn.GroupNorm(8, 48),
            nn.Mish(),
            nn.Conv2d(48, 32, kernel_size=3, padding=1),
            nn.Mish(),
        )
        self.out_proj = nn.Conv2d(32, 3, kernel_size=1)
        self.pressure_decoder = (
            nn.Sequential(
                nn.Conv2d(32, 32, kernel_size=3, padding=1),
                nn.GroupNorm(8, 32),
                nn.Mish(),
            )
            if self.split_heads
            else None
        )
        self.plume_decoder = (
            nn.Sequential(
                nn.Conv2d(32, 32, kernel_size=3, padding=1),
                nn.GroupNorm(8, 32),
                nn.Mish(),
                nn.Conv2d(32, 32, kernel_size=3, padding=1),
                nn.Mish(),
            )
            if self.split_heads
            else None
        )
        self.pressure_out = nn.Conv2d(32, 1, kernel_size=1) if self.split_heads else None
        self.z_out = nn.Conv2d(32, 1, kernel_size=1) if self.split_heads else None
        self.gas_support_out = nn.Conv2d(32, 1, kernel_size=1) if self.split_heads else None
        self.gas_amplitude_out = nn.Conv2d(32, 1, kernel_size=1) if self.split_heads else None
        self.transition_refine = (
            nn.Sequential(
                nn.Conv2d(32 + 7, 32, kernel_size=3, padding=1),
                nn.GroupNorm(8, 32),
                nn.Mish(),
                nn.Conv2d(32, 16, kernel_size=3, padding=1),
                nn.Mish(),
                nn.Conv2d(16, 2, kernel_size=1),
            )
            if self.use_transition_refine
            else None
        )
        self.oil_out = nn.Conv2d(32, 1, kernel_size=1) if self.use_production_v2 else None
        self.transition_gas_fraction = (
            nn.Sequential(
                nn.Conv2d(35, 32, kernel_size=3, padding=1),
                nn.GroupNorm(8, 32),
                nn.Mish(),
                nn.Conv2d(32, 1, kernel_size=1),
            )
            if self.use_transition_gas_fraction
            else None
        )
        production_head_dim = 32 + 32 + 4 + 2 + 16
        self.production_head = (
            nn.Sequential(
                nn.Linear(production_head_dim, 64),
                nn.SiLU(),
                nn.Linear(64, 32),
                nn.SiLU(),
                nn.Linear(32, 2),
            )
            if self.use_production_v2
            else None
        )
        if self.use_production_v2:
            self._init_production_v2_heads()
        if self.transition_gas_fraction is not None:
            self._init_transition_gas_fraction()
        stage_residual_channels = 4 if self.use_production_v2 else 3
        self.stage_expert_trunk = (
            nn.Sequential(
                nn.Conv2d(32, 32, kernel_size=3, padding=1),
                nn.GroupNorm(8, 32),
                nn.Mish(),
            )
            if self.use_stage_experts
            else None
        )
        self.stage_expert_heads = (
            nn.ModuleList(
                [
                    nn.Sequential(
                        nn.Conv2d(32, 16, kernel_size=3, padding=1),
                        nn.Mish(),
                        nn.Conv2d(16, stage_residual_channels, kernel_size=1),
                    )
                    for _ in range(3)
                ]
            )
            if self.use_stage_experts
            else None
        )
        if self.use_stage_experts:
            self._init_stage_experts()

    def _init_production_v2_heads(self) -> None:
        if self.oil_out is not None:
            nn.init.zeros_(self.oil_out.weight)
            nn.init.zeros_(self.oil_out.bias)
        if self.production_head is not None:
            final = self.production_head[-1]
            if isinstance(final, nn.Linear):
                nn.init.zeros_(final.weight)
                nn.init.constant_(final.bias, -8.0)

    def _init_transition_gas_fraction(self) -> None:
        if self.transition_gas_fraction is None:
            return
        final = self.transition_gas_fraction[-1]
        if isinstance(final, nn.Conv2d):
            nn.init.zeros_(final.weight)
            nn.init.zeros_(final.bias)

    def _init_stage_experts(self) -> None:
        if self.stage_expert_heads is None:
            return
        for head in self.stage_expert_heads:
            final = head[-1]
            if isinstance(final, nn.Conv2d):
                nn.init.zeros_(final.weight)
                nn.init.zeros_(final.bias)

    @staticmethod
    def _masked_mean(x: Tensor, mask: Tensor) -> Tensor:
        weight = mask.to(dtype=x.dtype)
        return (x * weight).sum(dim=(-2, -1)) / weight.sum(dim=(-2, -1)).clamp_min(1.0)

    def _control_context(self, last_frame: Tensor, transition_feat: Tensor | None) -> Tensor:
        batch = last_frame.shape[0]
        values: list[Tensor] = []

        def frame_values(start: int, end: int) -> Tensor:
            width = end - start
            if last_frame.shape[1] >= end:
                return last_frame[:, start:end, 0, 0]
            return last_frame.new_zeros(batch, width)

        values.append(frame_values(4, 7))
        values.append(frame_values(7, 9))
        values.append(frame_values(9, 11))
        values.append(frame_values(11, 13) if self.use_stage_progress_features else last_frame.new_zeros(batch, 2))
        if transition_feat is not None:
            values.append(transition_feat[:, :, 0, 0])
        else:
            values.append(last_frame.new_zeros(batch, 7))
        return torch.cat(values, dim=1)

    def _production_v2_aux(
        self,
        dec: Tensor,
        x_static: Tensor,
        last_frame: Tensor,
        pressure: Tensor,
        gas_sat: Tensor,
        z_co2: Tensor,
        oil_sat: Tensor,
        transition_feat: Tensor | None,
    ) -> dict[str, Tensor]:
        if self.oil_out is None or self.production_head is None:
            return {}
        completion_mask = x_static[:, 7:8]
        well_mask = x_static[:, 6:7]
        dec_pool = F.adaptive_avg_pool2d(dec, output_size=1).flatten(1)
        completion_dec = self._masked_mean(dec, completion_mask)
        near_state = torch.cat(
            [
                self._masked_mean(pressure, completion_mask),
                self._masked_mean(gas_sat, completion_mask),
                self._masked_mean(z_co2, completion_mask),
                self._masked_mean(oil_sat, completion_mask),
            ],
            dim=1,
        )
        mask_summary = torch.cat(
            [
                completion_mask.flatten(1).mean(dim=1, keepdim=True),
                well_mask.flatten(1).mean(dim=1, keepdim=True),
            ],
            dim=1,
        )
        head_input = torch.cat(
            [
                dec_pool,
                completion_dec,
                near_state,
                mask_summary,
                self._control_context(last_frame, transition_feat),
            ],
            dim=1,
        )
        return {"production_delta": F.softplus(self.production_head(head_input))}

    def _stage_expert_weights(
        self,
        last_frame: Tensor,
        transition_feat: Tensor | None,
        stage_context: Tensor | None,
    ) -> Tensor:
        batch = last_frame.shape[0]
        if stage_context is not None:
            stage = stage_context.to(device=last_frame.device)
            if stage.ndim > 1 and stage.shape[-1] == 3:
                weights = stage.to(dtype=last_frame.dtype)
                return weights / weights.sum(dim=1, keepdim=True).clamp_min(1e-6)
            stage = stage.reshape(-1).long()
            if stage.numel() == 1 and batch > 1:
                stage = stage.expand(batch)
            stage = stage[:batch].clamp(1, 3) - 1
            return F.one_hot(stage, num_classes=3).to(dtype=last_frame.dtype)
        if transition_feat is not None:
            weights = transition_feat[:, :3, 0, 0].to(dtype=last_frame.dtype)
            return weights / weights.sum(dim=1, keepdim=True).clamp_min(1e-6)
        if last_frame.shape[1] >= 7:
            weights = last_frame[:, 4:7, 0, 0].to(dtype=last_frame.dtype)
            return weights / weights.sum(dim=1, keepdim=True).clamp_min(1e-6)
        return last_frame.new_full((batch, 3), 1.0 / 3.0)

    def _apply_stage_experts(
        self,
        dec: Tensor,
        last_frame: Tensor,
        transition_feat: Tensor | None,
        stage_context: Tensor | None,
        pressure: Tensor,
        gas_sat: Tensor,
        z_co2: Tensor,
        oil_sat: Tensor | None = None,
    ) -> tuple[Tensor, Tensor, Tensor, Tensor | None, dict[str, Tensor]]:
        if self.stage_expert_trunk is None or self.stage_expert_heads is None:
            return pressure, gas_sat, z_co2, oil_sat, {}
        expert_feat = self.stage_expert_trunk(dec)
        residual_stack = torch.stack([head(expert_feat) for head in self.stage_expert_heads], dim=1)
        weights = self._stage_expert_weights(last_frame, transition_feat, stage_context)
        residual = (residual_stack * weights[:, :, None, None, None]).sum(dim=1) * self.stage_expert_scale

        pressure = pressure + residual[:, 0:1]
        gas_sat = torch.sigmoid(torch.logit(gas_sat.clamp(1e-4, 1.0 - 1e-4)) + residual[:, 1:2])
        z_co2 = torch.sigmoid(torch.logit(z_co2.clamp(1e-4, 1.0 - 1e-4)) + residual[:, 2:3])
        z_co2 = torch.maximum(z_co2, gas_sat)
        if oil_sat is not None and residual.shape[1] >= 4:
            oil_sat = torch.sigmoid(torch.logit(oil_sat.clamp(1e-4, 1.0 - 1e-4)) + residual[:, 3:4])
        return pressure, gas_sat, z_co2, oil_sat, {
            "stage_residual": residual,
            "stage_expert_weights": weights,
        }

    def _apply_transition_gas_fraction(
        self,
        dec: Tensor,
        last_frame: Tensor,
        stage_context: Tensor | None,
        gas_sat: Tensor,
        z_co2: Tensor,
    ) -> tuple[Tensor, dict[str, Tensor]]:
        if self.transition_gas_fraction is None:
            return gas_sat, {}
        batch = gas_sat.shape[0]
        if stage_context is None:
            produce_gate = gas_sat.new_zeros(batch, 1, 1, 1)
        elif stage_context.ndim > 1 and stage_context.shape[-1] == 3:
            produce_gate = stage_context[:, 2:3].to(device=gas_sat.device, dtype=gas_sat.dtype).view(batch, 1, 1, 1)
        else:
            stage = stage_context.reshape(-1).to(device=gas_sat.device)
            if stage.numel() == 1 and batch > 1:
                stage = stage.expand(batch)
            produce_gate = (stage[:batch].long() == 3).to(dtype=gas_sat.dtype).view(batch, 1, 1, 1)
        last_soak_gate = (
            (last_frame[:, 5:6] > 0.5).to(dtype=gas_sat.dtype)
            if last_frame.shape[1] > 5
            else gas_sat.new_zeros(batch, 1, *gas_sat.shape[-2:])
        )
        boundary_gate = produce_gate * last_soak_gate[:, :, :1, :1]
        if self.transition_gas_min_count_ratio > 0.0:
            last_gas_count = (last_frame[:, 1:2] >= 0.01).to(dtype=gas_sat.dtype).flatten(1).sum(dim=1, keepdim=True)
            last_z_count = (last_frame[:, 2:3] >= 0.02).to(dtype=gas_sat.dtype).flatten(1).sum(dim=1, keepdim=True)
            count_ratio = last_gas_count / last_z_count.clamp_min(1.0)
            dirty_gate = (count_ratio >= self.transition_gas_min_count_ratio).to(dtype=gas_sat.dtype).view(batch, 1, 1, 1)
            boundary_gate = boundary_gate * dirty_gate
        ratio_prior = (gas_sat / z_co2.clamp_min(1e-4)).clamp(1e-4, 1.0 - 1e-4)
        fraction_input = torch.cat([dec, last_frame[:, 1:2], gas_sat, z_co2], dim=1)
        ratio = torch.sigmoid(torch.logit(ratio_prior) + self.transition_gas_fraction(fraction_input))
        corrected_gas = (z_co2 * ratio).clamp(0.0, 1.0)
        gas_sat = torch.where(boundary_gate > 0.5, corrected_gas, gas_sat)
        return gas_sat, {
            "transition_gas_fraction": ratio,
            "transition_gas_fraction_gate": boundary_gate.expand_as(gas_sat),
        }

    def forward(
        self,
        x_dyn: Tensor,
        x_static: Tensor | None = None,
        *,
        stage_context: Tensor | None = None,
        return_aux: bool = False,
    ) -> Tensor | tuple[Tensor, dict[str, Tensor]]:
        if not self.use_static:
            x_dyn = x_dyn[:, :, :2]
        else:
            if self.use_production_v2 and x_static is None:
                raise ValueError("production_v2 output_contract requires x_static.")
            parts = [x_dyn[:, :, :13] if self.use_stage_progress_features else x_dyn[:, :, :11]]
            if self.use_transition_features:
                parts.append(x_dyn[:, :, 13:20])
            x_dyn = torch.cat(parts, dim=2)

        static_feat = self.static_encoder(x_static) if self.use_static and x_static is not None else None
        state_1: tuple[Tensor, Tensor] | None = None
        state_2: tuple[Tensor, Tensor] | None = None
        h1 = None

        for time_index in range(x_dyn.shape[1]):
            raw_t = x_dyn[:, time_index]
            x_t = raw_t
            if static_feat is not None:
                x_t = torch.cat([x_t, static_feat], dim=1)
            h1, c1 = self.conv_lstm_1(x_t, state_1)
            if self.use_film and self.film_1 is not None:
                cond = torch.stack(
                    [
                        raw_t[:, 4, 0, 0],
                        raw_t[:, 5, 0, 0],
                        raw_t[:, 6, 0, 0],
                        raw_t[:, 7, 0, 0],
                        raw_t[:, 8, 0, 0],
                        raw_t[:, 11, 0, 0],
                        raw_t[:, 12, 0, 0],
                    ],
                    dim=1,
                )
                h1 = self.film_1(h1, cond)
            state_1 = (h1, c1)

            h1_down = self.downsample(h1)
            h2, c2 = self.conv_lstm_2(h1_down, state_2)
            if self.use_film and self.film_2 is not None:
                h2 = self.film_2(h2, cond)
            state_2 = (h2, c2)

        if h1 is None or state_2 is None:
            raise RuntimeError("Sequence length must be at least 1.")

        h2 = self.bottleneck(state_2[0])
        up = self.up(h2)
        if up.shape[-2:] != h1.shape[-2:]:
            up = F.interpolate(up, size=h1.shape[-2:], mode="bilinear", align_corners=False)
        dec = self.decoder(torch.cat([up, h1], dim=1))
        last_pressure = x_dyn[:, -1, 0:1]
        last_gas = x_dyn[:, -1, 1:2].clamp(1e-4, 1.0 - 1e-4)
        last_z = x_dyn[:, -1, 2:3].clamp(1e-4, 1.0 - 1e-4) if self.use_static else x_dyn[:, -1, 1:2].clamp(1e-4, 1.0 - 1e-4)
        transition_feat = x_dyn[:, -1, -7:] if self.use_transition_features else None

        if not self.split_heads:
            out = self.out_proj(dec)
            pressure = last_pressure + out[:, 0:1]
            gas_sat = torch.sigmoid(torch.logit(last_gas) + out[:, 1:2])
            z_co2 = torch.sigmoid(torch.logit(last_z) + out[:, 2:3])
            if self.transition_refine is not None and transition_feat is not None:
                transition_gate = torch.clamp(
                    torch.maximum(transition_feat[:, 4:5], transition_feat[:, 6:7]) + 0.5 * transition_feat[:, 5:6],
                    0.0,
                    1.0,
                )
                refine_input = torch.cat([dec, transition_feat], dim=1)
                refine_delta = self.transition_refine(refine_input)
                gas_sat = torch.sigmoid(torch.logit(gas_sat.clamp(1e-4, 1.0 - 1e-4)) + transition_gate * refine_delta[:, 0:1])
                z_co2 = torch.sigmoid(torch.logit(z_co2.clamp(1e-4, 1.0 - 1e-4)) + transition_gate * refine_delta[:, 1:2])
            z_co2 = torch.maximum(z_co2, gas_sat)
            oil_sat: Tensor | None = None
            if self.use_production_v2:
                if self.oil_out is None or x_static is None:
                    raise RuntimeError("production_v2 path requires oil and production heads.")
                oil_prior = (1.0 - gas_sat).clamp(1e-4, 1.0 - 1e-4)
                oil_sat = torch.sigmoid(torch.logit(oil_prior) + self.oil_out(dec))

            pressure, gas_sat, z_co2, oil_sat, stage_aux = self._apply_stage_experts(
                dec,
                x_dyn[:, -1],
                transition_feat,
                stage_context,
                pressure,
                gas_sat,
                z_co2,
                oil_sat,
            )
            gas_sat, transition_gas_aux = self._apply_transition_gas_fraction(
                dec,
                x_dyn[:, -1],
                stage_context,
                gas_sat,
                z_co2,
            )

            if self.use_production_v2:
                if oil_sat is None or x_static is None:
                    raise RuntimeError("production_v2 path requires oil and production heads.")
                z_co2 = torch.maximum(z_co2, gas_sat)
                main = torch.cat([pressure, gas_sat, z_co2, oil_sat], dim=1)
                if return_aux:
                    aux = dict(stage_aux)
                    aux.update(transition_gas_aux)
                    aux.update(
                        self._production_v2_aux(
                            dec,
                            x_static,
                            x_dyn[:, -1],
                            pressure,
                            gas_sat,
                            z_co2,
                            oil_sat,
                            transition_feat,
                        )
                    )
                    return main, aux
                return main

            main = torch.cat([pressure, gas_sat, z_co2], dim=1)
            if return_aux:
                return main, stage_aux
            return main

        if self.pressure_decoder is None or self.plume_decoder is None:
            raise RuntimeError("Split-head path requires split-head modules.")

        pressure_feat = self.pressure_decoder(dec)
        plume_feat = self.plume_decoder(dec)
        pressure = last_pressure + self.pressure_out(pressure_feat)
        z_co2 = torch.sigmoid(torch.logit(last_z) + self.z_out(plume_feat))
        gas_support_logits = self.gas_support_out(plume_feat)
        gas_support_prob = torch.sigmoid(gas_support_logits)
        gas_amplitude = torch.sigmoid(torch.logit(last_gas) + self.gas_amplitude_out(plume_feat))
        gas_sat = torch.minimum(z_co2, gas_support_prob * gas_amplitude)
        if self.transition_refine is not None and transition_feat is not None:
            transition_gate = torch.clamp(
                torch.maximum(transition_feat[:, 4:5], transition_feat[:, 6:7]) + 0.5 * transition_feat[:, 5:6],
                0.0,
                1.0,
            )
            refine_input = torch.cat([dec, transition_feat], dim=1)
            refine_delta = self.transition_refine(refine_input)
            gas_sat = torch.sigmoid(torch.logit(gas_sat.clamp(1e-4, 1.0 - 1e-4)) + transition_gate * refine_delta[:, 0:1])
            z_co2 = torch.sigmoid(torch.logit(z_co2.clamp(1e-4, 1.0 - 1e-4)) + transition_gate * refine_delta[:, 1:2])
        z_co2 = torch.maximum(z_co2, gas_sat)
        oil_sat = None
        if self.use_production_v2:
            if self.oil_out is None or x_static is None:
                raise RuntimeError("production_v2 path requires oil and production heads.")
            oil_prior = (1.0 - gas_sat).clamp(1e-4, 1.0 - 1e-4)
            oil_sat = torch.sigmoid(torch.logit(oil_prior) + self.oil_out(dec))

        pressure, gas_sat, z_co2, oil_sat, stage_aux = self._apply_stage_experts(
            dec,
            x_dyn[:, -1],
            transition_feat,
            stage_context,
            pressure,
            gas_sat,
            z_co2,
            oil_sat,
        )
        gas_sat, transition_gas_aux = self._apply_transition_gas_fraction(
            dec,
            x_dyn[:, -1],
            stage_context,
            gas_sat,
            z_co2,
        )

        if self.use_production_v2:
            if oil_sat is None or x_static is None:
                raise RuntimeError("production_v2 path requires oil and production heads.")
            z_co2 = torch.maximum(z_co2, gas_sat)
            main = torch.cat([pressure, gas_sat, z_co2, oil_sat], dim=1)
            if return_aux:
                aux = {
                    "gas_support_logits": gas_support_logits,
                    "gas_support_prob": gas_support_prob,
                    "gas_amplitude": gas_amplitude,
                }
                aux.update(stage_aux)
                aux.update(transition_gas_aux)
                aux.update(
                    self._production_v2_aux(
                        dec,
                        x_static,
                        x_dyn[:, -1],
                        pressure,
                        gas_sat,
                        z_co2,
                        oil_sat,
                        transition_feat,
                    )
                )
                return main, aux
            return main

        main = torch.cat([pressure, gas_sat, z_co2], dim=1)
        if return_aux:
            aux = {
                "gas_support_logits": gas_support_logits,
                "gas_support_prob": gas_support_prob,
                "gas_amplitude": gas_amplitude,
            }
            aux.update(stage_aux)
            return main, aux
        return main


def sobel_gradients(x: Tensor) -> Tensor:
    kernel_x = torch.tensor(
        [[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]],
        device=x.device,
        dtype=x.dtype,
    ).view(1, 1, 3, 3) / 8.0
    kernel_y = torch.tensor(
        [[-1.0, -2.0, -1.0], [0.0, 0.0, 0.0], [1.0, 2.0, 1.0]],
        device=x.device,
        dtype=x.dtype,
    ).view(1, 1, 3, 3) / 8.0
    x_pad = F.pad(x, (1, 1, 1, 1), mode="replicate")
    grad_x = F.conv2d(x_pad, kernel_x, padding=0)
    grad_y = F.conv2d(x_pad, kernel_y, padding=0)
    return torch.cat([grad_x, grad_y], dim=1)


def _masked_huber(pred: Tensor, target: Tensor, mask: Tensor, delta: float) -> Tensor:
    weight = mask.to(dtype=pred.dtype)
    return (F.huber_loss(pred, target, delta=delta, reduction="none") * weight).sum() / weight.sum().clamp_min(1.0)


def _soft_dice(x: Tensor, y: Tensor, eps: float = 1e-6) -> Tensor:
    num = 2.0 * (x * y).sum(dim=(1, 2, 3)) + eps
    den = x.square().sum(dim=(1, 2, 3)) + y.square().sum(dim=(1, 2, 3)) + eps
    return 1.0 - (num / den).mean()


def _dilate_binary_mask(mask: Tensor, kernel_size: int = 3) -> Tensor:
    return F.max_pool2d(mask.float(), kernel_size=kernel_size, stride=1, padding=kernel_size // 2)


def focal_tversky_loss(
    prob: Tensor,
    target: Tensor,
    *,
    alpha: float = 0.3,
    beta: float = 0.7,
    gamma: float = 1.33,
    eps: float = 1e-6,
) -> Tensor:
    dims = (1, 2, 3)
    true_pos = (prob * target).sum(dim=dims)
    false_pos = (prob * (1.0 - target)).sum(dim=dims)
    false_neg = ((1.0 - prob) * target).sum(dim=dims)
    tversky = (true_pos + eps) / (true_pos + alpha * false_pos + beta * false_neg + eps)
    return torch.pow(1.0 - tversky, gamma).mean()


def model_a_loss(pred: Tensor, target: Tensor) -> tuple[Tensor, dict[str, float]]:
    loss = F.mse_loss(pred, target)
    return loss, {"loss_total": float(loss.detach().cpu().item()), "loss_mse": float(loss.detach().cpu().item())}


@dataclass
class PhysicsLossConfig:
    lambda_maps: float = 1.0
    lambda_plume: float = 0.2
    lambda_bounds: float = 0.1
    lambda_mass: float = 0.1
    lambda_grad: float = 0.05
    lambda_couple: float = 0.05
    lambda_darcy: float = 0.0
    lambda_gas_mass_match: float = 0.0
    lambda_z_mass_match: float = 0.0
    lambda_support_bce: float = 0.5
    lambda_support_tversky: float = 1.0
    lambda_gas_amp: float = 1.0
    lambda_gas_count: float = 0.2
    lambda_z_dice: float = 0.5
    use_support_head: bool = False
    use_production_v2: bool = False
    lambda_oil: float = 1.0
    lambda_production_delta: float = 1.0
    lambda_delta_oil: float = 1.0
    lambda_delta_gas: float = 1.0
    lambda_rate_delta: float = 0.1
    lambda_cumulative_monotonic: float = 0.01
    lambda_cumulative_match: float = 0.0
    lambda_phase: float = 0.05
    lambda_production_near_well: float = 0.05
    lambda_near_well_co2_gas: float = 0.05
    lambda_stage_residual: float = 0.01
    lambda_transition_gas_tversky: float = 0.0
    lambda_transition_gas_count: float = 0.0
    lambda_transition_gas_mass: float = 0.0
    lambda_transition_gas_active: float = 0.0


class HNPSprintLoss(nn.Module):
    def __init__(self, config: PhysicsLossConfig | None = None) -> None:
        super().__init__()
        self.config = config or PhysicsLossConfig()

    def forward(
        self,
        pred: Tensor,
        target: Tensor,
        *,
        last_frame: Tensor,
        stage_next: Tensor,
        static_maps: Tensor,
        pred_aux: dict[str, Tensor] | None = None,
        support_target: Tensor | None = None,
        production_delta_target: Tensor | None = None,
        production_delta_raw_target: Tensor | None = None,
        production_rate_target: Tensor | None = None,
        production_rate_raw_target: Tensor | None = None,
        dt_days: Tensor | None = None,
        production_delta_scale: Tensor | None = None,
        production_rate_scale: Tensor | None = None,
        pressure_scale: float = 1.0,
        z_scale: float = 1.0,
        gas_scale: float = 1.0,
        consistency_scale: float = 1.0,
    ) -> tuple[Tensor, dict[str, float]]:
        p_pred = pred[:, :1]
        sg_pred = pred[:, 1:2]
        z_pred = pred[:, 2:3]
        p_target = target[:, :1]
        sg_target = target[:, 1:2]
        z_target = target[:, 2:3]
        oil_pred = pred[:, 3:4] if pred.shape[1] >= 4 else None
        oil_target = target[:, 3:4] if target.shape[1] >= 4 else None
        p_last = last_frame[:, 0:1]
        sg_last = last_frame[:, 1:2]
        z_last = last_frame[:, 2:3]
        well_mask = static_maps[:, 6:7]
        completion_mask = static_maps[:, 7:8]
        plume_mask = ((sg_target > 0.01) | (z_target > 0.02)).float()
        pressure_weight = 1.0 + 1.5 * plume_mask + 2.0 * completion_mask + 1.0 * well_mask
        z_weight = 1.0 + 4.0 * (z_target > 0.02).float() + 2.0 * completion_mask

        def weighted_huber(x: Tensor, y: Tensor, weight: Tensor, delta: float = 0.1) -> Tensor:
            return (F.huber_loss(x, y, delta=delta, reduction="none") * weight).sum() / weight.sum().clamp_min(1.0)

        loss_pressure = weighted_huber(p_pred, p_target, pressure_weight, delta=0.2)
        loss_z = weighted_huber(z_pred, z_target, z_weight, delta=0.05)
        loss_z_dice = _soft_dice(z_pred, z_target)
        loss_oil = pred.new_tensor(0.0)
        loss_production_delta = pred.new_tensor(0.0)
        loss_delta_oil = pred.new_tensor(0.0)
        loss_delta_gas = pred.new_tensor(0.0)
        loss_rate_delta = pred.new_tensor(0.0)
        loss_phase = pred.new_tensor(0.0)
        loss_production_near_well = pred.new_tensor(0.0)
        loss_near_well_co2_gas = pred.new_tensor(0.0)
        loss_stage_residual = pred.new_tensor(0.0)
        loss_transition_gas_tversky = pred.new_tensor(0.0)
        loss_transition_gas_count = pred.new_tensor(0.0)
        loss_transition_gas_mass = pred.new_tensor(0.0)
        loss_transition_gas_active = pred.new_tensor(0.0)

        def masked_vector_huber(x: Tensor, y: Tensor, mask: Tensor, delta: float = 0.05) -> Tensor:
            loss_values = F.huber_loss(x, y, delta=delta, reduction="none")
            weight = mask.to(dtype=loss_values.dtype)
            return (loss_values * weight).sum() / weight.sum().clamp_min(1.0)

        if self.config.use_support_head and pred_aux is not None:
            if support_target is None:
                support_target = (sg_target >= 0.01).float()
            gas_support_logits = pred_aux["gas_support_logits"]
            gas_support_prob = pred_aux["gas_support_prob"]
            gas_amplitude = pred_aux["gas_amplitude"]
            support_target = support_target.float()
            amp_mask = _dilate_binary_mask(support_target, kernel_size=3)
            loss_support_bce = F.binary_cross_entropy_with_logits(gas_support_logits, support_target)
            loss_support_tversky = focal_tversky_loss(
                gas_support_prob,
                support_target,
                alpha=0.3,
                beta=0.7,
                gamma=1.33,
            )
            loss_gas_amp = _masked_huber(gas_amplitude, sg_target, amp_mask, delta=0.05)
            cell_scale = float(support_target.shape[-1] * support_target.shape[-2])
            support_count_pred = gas_support_prob.flatten(1).sum(dim=1) / cell_scale
            support_count_true = support_target.flatten(1).sum(dim=1) / cell_scale
            loss_gas_count = F.l1_loss(support_count_pred, support_count_true)
            loss_maps = pressure_scale * self.config.lambda_maps * loss_pressure + z_scale * self.config.lambda_maps * loss_z
            loss_plume = z_scale * self.config.lambda_z_dice * loss_z_dice
            loss_support = gas_scale * (
                self.config.lambda_support_bce * loss_support_bce
                + self.config.lambda_support_tversky * loss_support_tversky
                + self.config.lambda_gas_amp * loss_gas_amp
                + self.config.lambda_gas_count * loss_gas_count
            )
        else:
            sat_weight = 1.0 + 5.0 * plume_mask + 2.0 * completion_mask
            loss_maps = self.config.lambda_maps * (
                loss_pressure
                + 2.0 * weighted_huber(sg_pred, sg_target, sat_weight, delta=0.05)
                + 1.5 * loss_z
            )
            loss_plume = self.config.lambda_plume * (_soft_dice(sg_pred, sg_target) + 0.5 * _soft_dice(z_pred, z_target))
            loss_support_bce = pred.new_tensor(0.0)
            loss_support_tversky = pred.new_tensor(0.0)
            loss_gas_amp = pred.new_tensor(0.0)
            loss_gas_count = pred.new_tensor(0.0)
            loss_support = pred.new_tensor(0.0)

        if self.config.use_production_v2:
            if oil_pred is None or oil_target is None:
                raise ValueError("production_v2 loss requires 4-channel spatial predictions and targets.")
            if pred_aux is None or "production_delta" not in pred_aux:
                raise ValueError("production_v2 loss requires pred_aux['production_delta'].")
            if production_delta_target is None:
                raise ValueError("production_v2 loss requires production_delta_target.")

            oil_weight = 1.0 + 1.5 * plume_mask + 2.0 * completion_mask + 1.0 * well_mask
            loss_oil = weighted_huber(oil_pred, oil_target, oil_weight, delta=0.05)
            loss_maps = loss_maps + self.config.lambda_oil * loss_oil

            production_delta_pred = pred_aux["production_delta"]
            production_delta_target = production_delta_target.to(dtype=production_delta_pred.dtype)
            loss_delta_oil = F.huber_loss(
                production_delta_pred[:, 0],
                production_delta_target[:, 0],
                delta=0.05,
            )
            loss_delta_gas = F.huber_loss(
                production_delta_pred[:, 1],
                production_delta_target[:, 1],
                delta=0.05,
            )
            loss_production_delta = (
                self.config.lambda_delta_oil * loss_delta_oil
                + self.config.lambda_delta_gas * loss_delta_gas
            )

            if (
                production_rate_target is not None
                and dt_days is not None
                and production_delta_scale is not None
                and production_rate_scale is not None
            ):
                delta_scale = production_delta_scale.to(device=pred.device, dtype=production_delta_pred.dtype)
                rate_scale = production_rate_scale.to(device=pred.device, dtype=production_delta_pred.dtype)
                if delta_scale.ndim == 1:
                    delta_scale = delta_scale.unsqueeze(0)
                if rate_scale.ndim == 1:
                    rate_scale = rate_scale.unsqueeze(0)
                dt = dt_days.to(device=pred.device, dtype=production_delta_pred.dtype).reshape(-1, 1).clamp_min(1e-6)
                pred_rate_norm = (production_delta_pred * delta_scale / dt) / rate_scale.clamp_min(1e-6)
                rate_target = production_rate_target.to(device=pred.device, dtype=production_delta_pred.dtype)
                produce_weight = (stage_next.reshape(-1, 1) == 3).to(dtype=production_delta_pred.dtype)
                loss_rate_delta = masked_vector_huber(pred_rate_norm, rate_target, produce_weight.expand_as(rate_target), delta=0.05)

            loss_phase = (
                F.relu(-oil_pred)
                + F.relu(oil_pred - 1.0)
                + F.relu(sg_pred + oil_pred - 1.0)
                + F.relu(sg_pred - z_pred)
            ).mean()

            completion_weight = completion_mask.to(dtype=pred.dtype)
            completion_area = completion_weight.sum(dim=(-2, -1)).clamp_min(1.0)
            near_oil = (oil_pred * completion_weight).sum(dim=(-2, -1)) / completion_area
            near_gas = (sg_pred * completion_weight).sum(dim=(-2, -1)) / completion_area
            near_z = (z_pred * completion_weight).sum(dim=(-2, -1)) / completion_area
            oil_delta_pred = production_delta_pred[:, 0:1]
            gas_delta_pred = production_delta_pred[:, 1:2]
            loss_production_near_well = (
                oil_delta_pred * F.relu(0.05 - near_oil)
                + gas_delta_pred * F.relu(0.01 - near_gas)
            ).mean()
            loss_near_well_co2_gas = (
                gas_delta_pred * (F.relu(0.01 - near_gas) + F.relu(0.02 - near_z))
            ).mean()

        if pred_aux is not None and "stage_residual" in pred_aux:
            loss_stage_residual = pred_aux["stage_residual"].square().mean()

        loss_bounds = (
            F.relu(-sg_pred)
            + F.relu(sg_pred - 1.0)
            + F.relu(-z_pred)
            + F.relu(z_pred - 1.0)
            + F.relu(sg_pred - z_pred)
        ).mean()
        if oil_pred is not None:
            loss_bounds = loss_bounds + (F.relu(-oil_pred) + F.relu(oil_pred - 1.0)).mean()

        mass_pred = 0.5 * (sg_pred.flatten(1).mean(dim=1) + z_pred.flatten(1).mean(dim=1))
        mass_prev = 0.5 * (sg_last.flatten(1).mean(dim=1) + z_last.flatten(1).mean(dim=1))
        sg_mass_pred = sg_pred.flatten(1).sum(dim=1)
        sg_mass_target = sg_target.flatten(1).sum(dim=1)
        z_mass_pred = z_pred.flatten(1).sum(dim=1)
        z_mass_target = z_target.flatten(1).sum(dim=1)
        gas_mass_rel = (sg_mass_pred - sg_mass_target) / sg_mass_target.clamp_min(1.0)
        z_mass_rel = (z_mass_pred - z_mass_target) / z_mass_target.clamp_min(1.0)
        loss_gas_mass_match = F.huber_loss(gas_mass_rel, torch.zeros_like(gas_mass_rel), delta=0.25)
        loss_z_mass_match = F.huber_loss(z_mass_rel, torch.zeros_like(z_mass_rel), delta=0.25)
        boundary_mask = (stage_next == 3) & (last_frame[:, 5, 0, 0] > 0.5 if last_frame.shape[1] > 5 else stage_next.new_zeros(stage_next.shape, dtype=torch.bool))
        if (
            boundary_mask.any()
            and (
                self.config.lambda_transition_gas_tversky > 0.0
                or self.config.lambda_transition_gas_count > 0.0
                or self.config.lambda_transition_gas_mass > 0.0
                or self.config.lambda_transition_gas_active > 0.0
            )
        ):
            sg_boundary = sg_pred[boundary_mask]
            sg_target_boundary = sg_target[boundary_mask]
            support_boundary = (sg_target_boundary >= 0.01).to(dtype=sg_pred.dtype)
            support_prob = torch.sigmoid((sg_boundary - 0.01) / 0.005)
            loss_transition_gas_tversky = focal_tversky_loss(
                support_prob,
                support_boundary,
                alpha=0.75,
                beta=0.25,
                gamma=1.0,
            )
            pred_count = support_prob.flatten(1).sum(dim=1)
            true_count = support_boundary.flatten(1).sum(dim=1)
            count_rel = (pred_count - true_count) / true_count.clamp_min(1.0)
            loss_transition_gas_count = F.huber_loss(count_rel, torch.zeros_like(count_rel), delta=0.15)
            pred_mass = sg_boundary.flatten(1).sum(dim=1)
            true_mass = sg_target_boundary.flatten(1).sum(dim=1)
            mass_rel = (pred_mass - true_mass) / true_mass.clamp_min(1.0)
            loss_transition_gas_mass = F.huber_loss(mass_rel, torch.zeros_like(mass_rel), delta=0.15)
            active_weight = 1.0 + 12.0 * _dilate_binary_mask(support_boundary, kernel_size=3)
            loss_transition_gas_active = weighted_huber(
                sg_boundary,
                sg_target_boundary,
                active_weight,
                delta=0.03,
            )
        inject = stage_next == 1
        soak = stage_next == 2
        produce = stage_next == 3

        stage_mass = torch.zeros_like(mass_pred)
        stage_mass = torch.where(inject, F.relu(mass_prev - mass_pred), stage_mass)
        stage_mass = torch.where(soak, torch.abs(mass_pred - mass_prev), stage_mass)
        stage_mass = torch.where(produce, F.relu(mass_pred - mass_prev), stage_mass)
        loss_mass = stage_mass.mean()

        loss_grad = 0.7 * F.l1_loss(sobel_gradients(sg_pred), sobel_gradients(sg_target)) + 0.3 * F.l1_loss(
            sobel_gradients(z_pred),
            sobel_gradients(z_target),
        )
        delta_sg = sg_pred - sg_last
        delta_z = z_pred - z_last
        delta_p = p_pred - p_last
        delta_plume = 0.5 * (delta_sg + delta_z)
        loss_couple = F.relu(-(delta_plume * delta_p)).mean()

        if self.config.lambda_darcy > 0:
            grad_p = sobel_gradients(p_pred)
            grad_z = sobel_gradients(z_pred)
            perm_weight = torch.sigmoid(static_maps[:, 0:1] + 0.5 * static_maps[:, 3:4] - 0.5 * static_maps[:, 4:5])
            velocity = -perm_weight * grad_p
            alignment = (velocity * grad_z).sum(dim=1, keepdim=True)
            grad_norm = torch.linalg.vector_norm(grad_z, dim=1, keepdim=True)
            active_mask = ((z_pred > 0.02) & (grad_norm > 0.01)).float()
            loss_darcy = (F.relu(-alignment) * active_mask).mean()
        else:
            loss_darcy = pred.new_tensor(0.0)

        total = (
            loss_maps
            + loss_plume
            + loss_support
            + self.config.lambda_production_delta * loss_production_delta
            + consistency_scale
            * (
                self.config.lambda_bounds * loss_bounds
                + self.config.lambda_mass * loss_mass
                + self.config.lambda_grad * loss_grad
                + self.config.lambda_couple * loss_couple
                + self.config.lambda_darcy * loss_darcy
                + self.config.lambda_gas_mass_match * loss_gas_mass_match
                + self.config.lambda_z_mass_match * loss_z_mass_match
                + self.config.lambda_phase * loss_phase
                + self.config.lambda_production_near_well * loss_production_near_well
                + self.config.lambda_rate_delta * loss_rate_delta
                + self.config.lambda_near_well_co2_gas * loss_near_well_co2_gas
                + self.config.lambda_stage_residual * loss_stage_residual
                + self.config.lambda_transition_gas_tversky * loss_transition_gas_tversky
                + self.config.lambda_transition_gas_count * loss_transition_gas_count
                + self.config.lambda_transition_gas_mass * loss_transition_gas_mass
                + self.config.lambda_transition_gas_active * loss_transition_gas_active
            )
        )
        loss_dict = {
            "loss_total": float(total.detach().cpu().item()),
            "loss_maps": float(loss_maps.detach().cpu().item()),
            "loss_plume": float(loss_plume.detach().cpu().item()),
            "loss_bounds": float(loss_bounds.detach().cpu().item()),
            "loss_mass": float(loss_mass.detach().cpu().item()),
            "loss_grad": float(loss_grad.detach().cpu().item()),
            "loss_couple": float(loss_couple.detach().cpu().item()),
            "loss_darcy": float(loss_darcy.detach().cpu().item()),
            "loss_gas_mass_match": float(loss_gas_mass_match.detach().cpu().item()),
            "loss_z_mass_match": float(loss_z_mass_match.detach().cpu().item()),
            "loss_support_bce": float(loss_support_bce.detach().cpu().item()),
            "loss_support_tversky": float(loss_support_tversky.detach().cpu().item()),
            "loss_gas_amp": float(loss_gas_amp.detach().cpu().item()),
            "loss_gas_count": float(loss_gas_count.detach().cpu().item()),
            "loss_pressure": float(loss_pressure.detach().cpu().item()),
            "loss_z": float(loss_z.detach().cpu().item()),
            "loss_z_dice": float(loss_z_dice.detach().cpu().item()),
            "loss_oil": float(loss_oil.detach().cpu().item()),
            "loss_production_delta": float(loss_production_delta.detach().cpu().item()),
            "loss_delta_oil": float(loss_delta_oil.detach().cpu().item()),
            "loss_delta_gas": float(loss_delta_gas.detach().cpu().item()),
            "loss_rate_delta": float(loss_rate_delta.detach().cpu().item()),
            "loss_phase": float(loss_phase.detach().cpu().item()),
            "loss_production_near_well": float(loss_production_near_well.detach().cpu().item()),
            "loss_near_well_co2_gas": float(loss_near_well_co2_gas.detach().cpu().item()),
            "loss_cumulative_monotonic": 0.0,
            "loss_stage_residual": float(loss_stage_residual.detach().cpu().item()),
            "loss_transition_gas_tversky": float(loss_transition_gas_tversky.detach().cpu().item()),
            "loss_transition_gas_count": float(loss_transition_gas_count.detach().cpu().item()),
            "loss_transition_gas_mass": float(loss_transition_gas_mass.detach().cpu().item()),
            "loss_transition_gas_active": float(loss_transition_gas_active.detach().cpu().item()),
        }
        return total, loss_dict
