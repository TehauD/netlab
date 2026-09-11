"""Statistical primitives.

Deliberately stdlib-only and side-effect free. Every function is a pure transformation
over a sequence of numbers, which makes them trivially unit-testable and safe to reuse in
a pipeline, a notebook, or a serverless function.

References for the estimators used:
  * Shannon entropy / Pielou evenness  -- standard ecological diversity measures.
  * Hill numbers (effective counts)    -- Jost (2006), "Entropy and diversity".
  * Herfindahl-Hirschman Index         -- antitrust concentration measure, rescaled to 0-1.
  * Discrete power-law MLE             -- Clauset, Shalizi & Newman (2009), continuous
                                          approximation with the x_min - 0.5 correction.
  * Robust z-score via MAD             -- Iglewicz & Hoaglin modified z-score.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _clean(values: Sequence[float]) -> list[float]:
    return [float(v) for v in values if v is not None and not math.isnan(float(v))]


# --------------------------------------------------------------------------------------
# Concentration and diversity
# --------------------------------------------------------------------------------------

def gini(values: Sequence[float]) -> float:
    """Gini coefficient of a non-negative distribution. 0 = perfectly even, 1 = fully concentrated."""
    v = sorted(x for x in _clean(values) if x >= 0)
    n = len(v)
    if n == 0:
        return 0.0
    total = sum(v)
    if total == 0:
        return 0.0
    cumulative = sum((i + 1) * x for i, x in enumerate(v))
    return round((2 * cumulative) / (n * total) - (n + 1) / n, 4)


def hhi(values: Sequence[float]) -> float:
    """Normalized Herfindahl-Hirschman Index in [0, 1].

    0 approaches perfect fragmentation; 1 means a single entity holds everything.
    Normalization removes the dependence on the number of categories, so the value is
    comparable across networks of different sizes.
    """
    v = [x for x in _clean(values) if x > 0]
    n = len(v)
    if n <= 1:
        return 1.0 if n == 1 else 0.0
    total = sum(v)
    raw = sum((x / total) ** 2 for x in v)
    return round(max((raw - 1 / n) / (1 - 1 / n), 0.0), 4)


def shannon_entropy(values: Sequence[float], base: float = math.e) -> float:
    """Shannon entropy H of a count distribution."""
    v = [x for x in _clean(values) if x > 0]
    total = sum(v)
    if total <= 0 or len(v) <= 1:
        return 0.0
    h = -sum((x / total) * math.log(x / total, base) for x in v)
    return round(h, 4)


def pielou_evenness(values: Sequence[float]) -> float:
    """H / H_max in [0, 1]. Answers: is the network spread evenly, or lumpy?"""
    v = [x for x in _clean(values) if x > 0]
    if len(v) <= 1:
        return 0.0
    return round(shannon_entropy(v) / math.log(len(v)), 4)


def effective_count(values: Sequence[float]) -> float:
    """Hill number of order 1: exp(H).

    The intuition that makes this worth reporting -- "you have 300 employers on paper but
    effectively only 42 that matter" -- is far more interpretable than raw entropy.
    """
    v = [x for x in _clean(values) if x > 0]
    if not v:
        return 0.0
    return round(math.exp(shannon_entropy(v)), 2)


def top_k_share(values: Sequence[float], k: int = 10) -> float:
    """Share of total mass held by the k largest categories."""
    v = sorted((x for x in _clean(values) if x > 0), reverse=True)
    total = sum(v)
    if total <= 0:
        return 0.0
    return round(sum(v[:k]) / total, 4)


def powerlaw_alpha(values: Sequence[float], x_min: float = 1.0) -> float | None:
    """Discrete power-law exponent via the continuous MLE with the (x_min - 0.5) correction.

    Returns None when the tail is too thin for the estimate to mean anything (n < 10).
    An alpha near 2 indicates a heavy-tailed, hub-dominated structure; alpha > 3.5
    indicates a distribution with no meaningful tail.
    """
    tail = [x for x in _clean(values) if x >= x_min]
    n = len(tail)
    if n < 10:
        return None
    shift = x_min - 0.5
    denom = sum(math.log(x / shift) for x in tail)
    if denom <= 0:
        return None
    return round(1 + n / denom, 3)


# --------------------------------------------------------------------------------------
# Central tendency and dispersion
# --------------------------------------------------------------------------------------

def median(values: Sequence[float]) -> float:
    v = sorted(_clean(values))
    n = len(v)
    if n == 0:
        return 0.0
    mid = n // 2
    return v[mid] if n % 2 else (v[mid - 1] + v[mid]) / 2


def mad(values: Sequence[float]) -> float:
    """Median absolute deviation -- outlier-resistant dispersion."""
    v = _clean(values)
    if not v:
        return 0.0
    m = median(v)
    return median([abs(x - m) for x in v])


def modified_zscores(values: Sequence[float]) -> list[float]:
    """Iglewicz-Hoaglin modified z-scores. |z| > 3.5 is the conventional outlier threshold.

    Used here for burst detection on monthly connection counts, where the mean/stdev
    z-score would be dragged around by the very bursts we are trying to find.
    """
    v = _clean(values)
    if not v:
        return []
    m = median(v)
    d = mad(v)
    if d == 0:
        # Degenerate spread: fall back to a mean-absolute-deviation scale.
        mean_abs = sum(abs(x - m) for x in v) / len(v)
        if mean_abs == 0:
            return [0.0] * len(v)
        return [round(0.7979 * (x - m) / mean_abs, 3) for x in v]
    return [round(0.6745 * (x - m) / d, 3) for x in v]


def ols_slope(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float]:
    """Ordinary least squares fit. Returns (slope, intercept, r_squared).

    Used to test directional drift -- e.g. "is the mean seniority of new connections
    rising year over year?" -- without pulling in numpy.
    """
    x, y = _clean(xs), _clean(ys)
    n = min(len(x), len(y))
    if n < 2:
        return 0.0, 0.0, 0.0
    x, y = x[:n], y[:n]
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        return 0.0, my, 0.0
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    slope = sxy / sxx
    intercept = my - slope * mx
    syy = sum((yi - my) ** 2 for yi in y)
    r2 = 0.0 if syy == 0 else max(min((sxy**2) / (sxx * syy), 1.0), 0.0)
    return round(slope, 4), round(intercept, 4), round(r2, 4)


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile. `p` in [0, 100]."""
    v = sorted(_clean(values))
    if not v:
        return 0.0
    k = (len(v) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return v[int(k)]
    return v[lo] * (hi - k) + v[hi] * (k - lo)
