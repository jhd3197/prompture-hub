"""Token prices for a model string, as Prompture's rate tables know them.

``model_rates`` answers "what could a call to this model cost?" so the quota
layer can reserve headroom before the call, and refuse models whose spend
could never be metered.

- Local providers (Ollama, LM Studio, ...) are free: priced at 0, not unknown.
- A model with explicit zero rates is known.
- A model with no rates is unknown (``None``).
- Virtual models resolve conservatively: a ``combo/`` or ``auto/`` route is
  unknown if ANY of its targets is unknown, otherwise it is priced at the
  component-wise most expensive target (any target may serve the call). A
  ``fusion/`` call runs its whole panel and the judge, so those prices add up.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Providers whose Prompture drivers declare zero-cost pricing.
LOCAL_PROVIDERS = frozenset(
    {"ollama", "lmstudio", "lm_studio", "lm-studio", "local_http", "airllm", "huggingface", "hf", "claude-code", "codex"}
)
_MAX_DEPTH = 3


@dataclass(frozen=True)
class Rates:
    """USD per 1M tokens."""

    input: float
    output: float

    @property
    def free(self) -> bool:
        return self.input == 0 and self.output == 0

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input + output_tokens * self.output) / 1_000_000


def _leaf_rates(model: str) -> Rates | None:
    provider, _, model_id = model.partition("/")
    if provider == "openai_compatible" and "/" in model_id:
        provider, _, model_id = model_id.partition("/")  # openai_compatible/<profile>/<model>
    if provider.lower() in LOCAL_PROVIDERS:
        return Rates(0.0, 0.0)
    from prompture.infra.model_rates import get_model_rates

    try:
        found = get_model_rates(provider, model_id)
    except Exception:  # a broken rate source must not take chat down; treat as unknown
        return None
    if not found or found.get("input") is None or found.get("output") is None:
        return None
    return Rates(float(found["input"]), float(found["output"]))


def _targets(resolved: str) -> tuple[list[str], bool] | None:
    """``(target models, additive)`` for a virtual model, ``None`` for an ordinary one."""
    if resolved.startswith("combo/"):
        from prompture.resilience import get_combo

        combo = get_combo(resolved)
        return ([t if isinstance(t, str) else t.model for t in combo.targets] if combo else []), False
    if resolved.startswith("auto/"):
        from prompture.resilience import auto_targets

        try:
            return auto_targets(resolved[len("auto/"):]), False
        except ValueError:
            return [], False
    if resolved.startswith("fusion/"):
        from prompture.groups.fusion import get_fusion

        spec = get_fusion(resolved)
        return ([*spec.panel, spec.judge] if spec else []), True
    return None


def model_rates(model: str, _depth: int = 0) -> Rates | None:
    """Rates for *model*, or ``None`` when its pricing is unknown."""
    from prompture.resilience import resolve_model_alias

    resolved = resolve_model_alias(model)
    virtual = _targets(resolved) if _depth < _MAX_DEPTH else None
    if virtual is None:
        return _leaf_rates(resolved)
    targets, additive = virtual
    rates = [model_rates(t, _depth + 1) for t in targets]
    if not rates or any(r is None for r in rates):
        return None
    pick = sum if additive else max
    return Rates(pick(r.input for r in rates), pick(r.output for r in rates))
