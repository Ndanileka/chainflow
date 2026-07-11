from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import ceil, floor
import random


class SentimentState(str, Enum):
    """Market sentiment state machine for the Ponzi lifecycle."""
    OPTIMISTIC = "optimistic"   # Early days, cash pool growing steadily
    FOMO = "fomo"               # Cash pool growing fast, recruitment boosted 1.5x
    CONCERN = "concern"         # Cash pool shrinking, recruitment drops 50%
    PANIC = "panic"             # Cash pool critical, recruitment near 0, withdrawals spike
    COLLAPSED = "collapsed"     # Insolvency reached


# Sentiment thresholds (health_ratio = cash_pool / upcoming_payouts)
FOMO_THRESHOLD = 3.0        # 3x reserves vs payouts → euphoria
CONCERN_THRESHOLD = 1.5     # 1.5x reserves → worry begins
PANIC_THRESHOLD = 0.8       # Less than 80% coverage → bank run

# Sentiment multipliers on recruitment
FOMO_RECRUITMENT_BOOST = 1.5
CONCERN_RECRUITMENT_PENALTY = 0.5
PANIC_RECRUITMENT_PENALTY = 0.05   # Near-zero new inflows

# Stochastic early withdrawal rates (fraction of unpaid participants who panic-withdraw)
CONCERN_EARLY_WITHDRAWAL_RATE = 0.02   # 2% per period
PANIC_EARLY_WITHDRAWAL_RATE = 0.15     # 15% per period (bank run)


@dataclass(frozen=True)
class SimulationParameters:
    initial_participants: int
    contribution_amount: float
    promised_return: float
    recruitment_rate: float
    recruitment_model: str
    population_limit: int
    time_interval: str
    currency: str = "USD"
    max_periods: int = 52
    payout_delay: int = 2
    enable_sentiment: bool = True  # Toggle psychology engine


@dataclass
class ParticipantBatch:
    period: int
    count: int
    contribution: float
    payout_due_period: int
    payout_per_participant: float
    paid: bool = False

    @property
    def total_payout_due(self) -> float:
        return self.count * self.payout_per_participant


@dataclass(frozen=True)
class TimelineState:
    period: int
    label: str
    new_participants: int
    total_participants: int
    cash_pool: float
    total_contributions: float
    total_payouts: float
    profitable_participants: int
    losing_participants: int
    pending_payouts: float
    required_recruits: int
    collapse: bool
    # New sentiment & analytics fields
    sentiment: str              # SentimentState value
    health_ratio: float         # cash_pool / upcoming_payouts_next_period
    inflow: float               # Capital inflow this period
    outflow: float              # Capital outflow this period
    peak_cash_pool: float       # Highest cash pool seen so far
    early_withdrawals: int      # Stochastic early withdrawals this period


@dataclass(frozen=True)
class SimulationSummary:
    total_participants: int
    cash_pool: float
    total_contributions: float
    total_payouts: float
    profitable_participants: int
    losing_participants: int
    collapse_period: int | None
    collapse_label: str
    sustainability_ratio: float
    peak_cash_pool: float
    peak_period: int | None
    total_early_withdrawals: int
    currency: str = "USD"


def run_simulation(params: SimulationParameters) -> dict[str, object]:
    normalized = _normalize(params)
    timeline_builder = Timeline(normalized)
    timeline = timeline_builder.run()
    summary = _summarize(timeline, normalized)

    return {
        "is_monte_carlo": False,
        "timeline": [asdict(state) for state in timeline],
        "summary": asdict(summary),
    }


def run_monte_carlo(params: SimulationParameters, iterations: int = 500) -> dict[str, object]:
    normalized = _normalize(params)
    collapse_periods = []
    max_cash_pools = []
    profitable_ratios = []

    for _ in range(iterations):
        # Apply Gaussian noise (15% standard deviation) to key parameters
        mc_params = SimulationParameters(
            initial_participants=normalized.initial_participants,
            contribution_amount=max(0.01, random.gauss(normalized.contribution_amount, normalized.contribution_amount * 0.15)),
            promised_return=normalized.promised_return,
            recruitment_rate=max(0.0, random.gauss(normalized.recruitment_rate, normalized.recruitment_rate * 0.15)),
            recruitment_model=normalized.recruitment_model,
            population_limit=normalized.population_limit,
            time_interval=normalized.time_interval,
            currency=normalized.currency,
            max_periods=normalized.max_periods,
            payout_delay=normalized.payout_delay,
            enable_sentiment=normalized.enable_sentiment,
        )
        
        timeline_builder = Timeline(mc_params)
        timeline = timeline_builder.run()
        summary = _summarize(timeline, mc_params)
        
        collapse_periods.append(summary.collapse_period if summary.collapse_period is not None else normalized.max_periods)
        max_cash_pools.append(max(state.cash_pool for state in timeline) if timeline else 0)
        
        total_p = summary.total_participants or 1
        profitable_ratios.append(summary.profitable_participants / total_p)

    histogram = {}
    for p in collapse_periods:
        histogram[p] = histogram.get(p, 0) + 1

    hist_labels = []
    hist_data = []
    for p in range(1, normalized.max_periods + 1):
        hist_labels.append(f"{normalized.time_interval.title()[:3]} {p}")
        hist_data.append(histogram.get(p, 0))

    avg_collapse = sum(collapse_periods) / iterations
    avg_max_pool = sum(max_cash_pools) / iterations
    avg_profitable = sum(profitable_ratios) / iterations
    survived = histogram.get(normalized.max_periods, 0)

    return {
        "is_monte_carlo": True,
        "iterations": iterations,
        "summary": {
            "avg_collapse_period": round(avg_collapse, 1),
            "avg_max_cash_pool": avg_max_pool,
            "avg_profitable_ratio": round(avg_profitable * 100, 1),
            "survival_rate": round((survived / iterations) * 100, 1),
            "time_interval": normalized.time_interval,
            "currency": normalized.currency
        },
        "histogram": {
            "labels": hist_labels,
            "data": hist_data
        }
    }


def _normalize(params: SimulationParameters) -> SimulationParameters:
    return SimulationParameters(
        initial_participants=max(1, int(params.initial_participants)),
        contribution_amount=max(0.01, float(params.contribution_amount)),
        promised_return=max(1.0, float(params.promised_return)),
        recruitment_rate=max(0.0, float(params.recruitment_rate)),
        recruitment_model=params.recruitment_model
        if params.recruitment_model in {"exponential", "linear", "saturating"}
        else "exponential",
        population_limit=max(1, int(params.population_limit)),
        time_interval=params.time_interval or "period",
        currency=params.currency if params.currency in {"USD", "ZAR"} else "USD",
        max_periods=max(1, min(520, int(params.max_periods))),
        payout_delay=max(1, min(52, int(params.payout_delay))),
        enable_sentiment=params.enable_sentiment,
    )


class Recruitment:
    def __init__(self, params: SimulationParameters) -> None:
        self.params = params

    def next_count(
        self,
        previous_new: int,
        total_participants: int,
        period: int,
        sentiment_multiplier: float = 1.0,
    ) -> int:
        remaining = self.params.population_limit - total_participants
        if remaining <= 0:
            return 0

        if self.params.recruitment_model == "linear":
            projected = self.params.initial_participants * self.params.recruitment_rate
        elif self.params.recruitment_model == "saturating":
            saturation = max(0.0, remaining / self.params.population_limit)
            projected = previous_new * self.params.recruitment_rate * saturation
        else:
            projected = previous_new * self.params.recruitment_rate

        # Apply sentiment multiplier (FOMO boost or FUD penalty)
        projected *= sentiment_multiplier

        if period > 1 and projected > 0:
            projected = max(1, projected)

        return min(remaining, floor(projected))


class CashPool:
    def __init__(self) -> None:
        self.balance = 0.0
        self.total_contributions = 0.0
        self.total_payouts = 0.0

    def contribute(self, amount: float) -> None:
        self.balance += amount
        self.total_contributions += amount

    def pay_due_batches(self, batches: list[ParticipantBatch], period: int) -> int:
        profitable = 0
        for batch in batches:
            if batch.paid or batch.payout_due_period > period:
                continue
            if self.balance < batch.total_payout_due:
                continue
            self.balance -= batch.total_payout_due
            self.total_payouts += batch.total_payout_due
            batch.paid = True
            profitable += batch.count
        return profitable

    def process_early_withdrawals(self, amount: float) -> float:
        """Process panic-driven early withdrawals (principal only, no return)."""
        actual = min(amount, self.balance)
        self.balance -= actual
        self.total_payouts += actual
        return actual


class SentimentEngine:
    """Determines the psychological state of the market based on financial health."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.state = SentimentState.OPTIMISTIC
        self.declining_periods = 0  # Consecutive periods of cash pool decline
        self.previous_cash_pool = 0.0

    def evaluate(self, cash_pool: float, upcoming_payouts: float, period: int) -> SentimentState:
        """Evaluate sentiment based on health ratio and trend."""
        if not self.enabled:
            return SentimentState.OPTIMISTIC

        # Track cash pool trend
        if period > 0:
            if cash_pool < self.previous_cash_pool:
                self.declining_periods += 1
            else:
                self.declining_periods = 0
        self.previous_cash_pool = cash_pool

        # Calculate health ratio
        health_ratio = cash_pool / upcoming_payouts if upcoming_payouts > 0 else 999.0

        # State transitions (with hysteresis via declining_periods)
        if health_ratio >= FOMO_THRESHOLD and self.declining_periods == 0:
            self.state = SentimentState.FOMO
        elif health_ratio >= CONCERN_THRESHOLD:
            # If declining for 2+ periods, shift to CONCERN even if ratio is OK
            if self.declining_periods >= 2:
                self.state = SentimentState.CONCERN
            elif self.state == SentimentState.CONCERN:
                # Stay in concern (don't bounce back to optimistic easily)
                self.state = SentimentState.CONCERN
            else:
                self.state = SentimentState.OPTIMISTIC
        elif health_ratio >= PANIC_THRESHOLD:
            self.state = SentimentState.CONCERN
        else:
            self.state = SentimentState.PANIC

        return self.state

    def get_recruitment_multiplier(self) -> float:
        """Return the recruitment rate multiplier based on current sentiment."""
        if self.state == SentimentState.FOMO:
            return FOMO_RECRUITMENT_BOOST
        elif self.state == SentimentState.CONCERN:
            return CONCERN_RECRUITMENT_PENALTY
        elif self.state == SentimentState.PANIC:
            return PANIC_RECRUITMENT_PENALTY
        return 1.0  # OPTIMISTIC

    def get_early_withdrawal_rate(self) -> float:
        """Return the fraction of unpaid participants who panic-withdraw."""
        if self.state == SentimentState.CONCERN:
            return CONCERN_EARLY_WITHDRAWAL_RATE
        elif self.state == SentimentState.PANIC:
            return PANIC_EARLY_WITHDRAWAL_RATE
        return 0.0  # No early withdrawals in OPTIMISTIC or FOMO


class Timeline:
    def __init__(self, params: SimulationParameters) -> None:
        self.params = params
        self.recruitment = Recruitment(params)
        self.cash_pool = CashPool()
        self.batches: list[ParticipantBatch] = []
        self.profitable_participants = 0
        self.collapse_period: int | None = None
        self.sentiment_engine = SentimentEngine(enabled=params.enable_sentiment)
        self.peak_cash_pool = 0.0
        self.peak_period: int | None = None
        self.total_early_withdrawals = 0

    def run(self) -> list[TimelineState]:
        states: list[TimelineState] = []
        total_participants = 0
        previous_new = self.params.initial_participants

        for period in range(self.params.max_periods + 1):
            # --- 1. Calculate upcoming payouts (next period lookahead) ---
            upcoming_payouts = sum(
                batch.total_payout_due
                for batch in self.batches
                if not batch.paid and batch.payout_due_period <= period + 1
            )

            # --- 2. Evaluate sentiment BEFORE recruitment ---
            sentiment = self.sentiment_engine.evaluate(
                self.cash_pool.balance, upcoming_payouts, period
            )
            recruitment_multiplier = self.sentiment_engine.get_recruitment_multiplier()

            # --- 3. Recruit new participants (sentiment-adjusted) ---
            new_participants = (
                self.params.initial_participants
                if period == 0
                else self.recruitment.next_count(
                    previous_new, total_participants, period, recruitment_multiplier
                )
            )
            total_participants += new_participants
            previous_new = new_participants

            # --- 4. Process inflows (new contributions) ---
            inflow = new_participants * self.params.contribution_amount
            self._add_batch(period, new_participants)

            # --- 5. Process stochastic early withdrawals (panic selling) ---
            early_withdrawal_rate = self.sentiment_engine.get_early_withdrawal_rate()
            early_withdrawals = 0
            if early_withdrawal_rate > 0 and period > 0:
                # Count unpaid participants who haven't matured yet
                unpaid_immature_count = sum(
                    batch.count for batch in self.batches
                    if not batch.paid and batch.payout_due_period > period
                )
                # Stochastic: each unpaid participant has a chance to panic-withdraw
                early_withdrawals = int(unpaid_immature_count * early_withdrawal_rate)
                if early_withdrawals > 0:
                    # They withdraw principal only (no return) — a partial loss
                    withdrawal_amount = early_withdrawals * self.params.contribution_amount
                    self.cash_pool.process_early_withdrawals(withdrawal_amount)
                    self.total_early_withdrawals += early_withdrawals

            # --- 6. Calculate required recruits to prevent collapse ---
            due_unpaid = [
                batch for batch in self.batches
                if not batch.paid and batch.payout_due_period <= period
            ]
            payouts_due = sum(batch.total_payout_due for batch in due_unpaid)
            current_balance = self.cash_pool.balance
            deficit = max(0.0, payouts_due - current_balance)
            required_recruits = int(ceil(deficit / self.params.contribution_amount)) if deficit > 0 else 0

            # --- 7. Process scheduled payouts ---
            prev_total_payouts = self.cash_pool.total_payouts
            self.profitable_participants += self.cash_pool.pay_due_batches(
                self.batches, period
            )
            outflow = self.cash_pool.total_payouts - prev_total_payouts

            # --- 8. Track peak liquidity ---
            if self.cash_pool.balance > self.peak_cash_pool:
                self.peak_cash_pool = self.cash_pool.balance
                self.peak_period = period

            # --- 9. Calculate health ratio ---
            health_ratio = (
                self.cash_pool.balance / upcoming_payouts
                if upcoming_payouts > 0
                else 999.0
            )

            # --- 10. Check for collapse ---
            pending_payouts = sum(
                batch.total_payout_due for batch in self.batches if not batch.paid
            )
            losing_participants = total_participants - self.profitable_participants
            collapse = self._has_collapsed(period, new_participants)
            if collapse and self.collapse_period is None:
                self.collapse_period = period
                sentiment = SentimentState.COLLAPSED

            states.append(
                TimelineState(
                    period=period,
                    label=f"{self.params.time_interval.title()} {period}",
                    new_participants=new_participants,
                    total_participants=total_participants,
                    cash_pool=round(self.cash_pool.balance, 2),
                    total_contributions=round(self.cash_pool.total_contributions, 2),
                    total_payouts=round(self.cash_pool.total_payouts, 2),
                    profitable_participants=self.profitable_participants,
                    losing_participants=losing_participants,
                    pending_payouts=round(pending_payouts, 2),
                    required_recruits=required_recruits,
                    collapse=collapse,
                    sentiment=sentiment.value,
                    health_ratio=round(health_ratio, 2),
                    inflow=round(inflow, 2),
                    outflow=round(outflow, 2),
                    peak_cash_pool=round(self.peak_cash_pool, 2),
                    early_withdrawals=early_withdrawals,
                )
            )

            if collapse:
                break

        return states

    def _add_batch(self, period: int, count: int) -> None:
        if count <= 0:
            return
        contribution = count * self.params.contribution_amount
        self.cash_pool.contribute(contribution)
        self.batches.append(
            ParticipantBatch(
                period=period,
                count=count,
                contribution=contribution,
                payout_due_period=period + self.params.payout_delay,
                payout_per_participant=ceil(
                    self.params.contribution_amount * self.params.promised_return
                ),
            )
        )

    def _has_collapsed(self, period: int, new_participants: int) -> bool:
        due_unpaid = [
            batch for batch in self.batches if not batch.paid and batch.payout_due_period <= period
        ]
        cannot_pay_due = any(
            self.cash_pool.balance < batch.total_payout_due for batch in due_unpaid
        )
        return cannot_pay_due


def _summarize(
    timeline: list[TimelineState],
    params: SimulationParameters,
) -> SimulationSummary:
    last = timeline[-1]
    collapse_period = next((state.period for state in timeline if state.collapse), None)
    collapse_label = (
        f"{params.time_interval.title()} {collapse_period}"
        if collapse_period is not None
        else "No collapse within simulation"
    )
    sustainability_ratio = (
        last.total_contributions / last.pending_payouts if last.pending_payouts else 1.0
    )

    # Find the peak
    peak_state = max(timeline, key=lambda s: s.cash_pool)

    return SimulationSummary(
        total_participants=last.total_participants,
        cash_pool=last.cash_pool,
        total_contributions=last.total_contributions,
        total_payouts=last.total_payouts,
        profitable_participants=last.profitable_participants,
        losing_participants=last.losing_participants,
        collapse_period=collapse_period,
        collapse_label=collapse_label,
        sustainability_ratio=round(sustainability_ratio, 2),
        peak_cash_pool=round(peak_state.cash_pool, 2),
        peak_period=peak_state.period,
        total_early_withdrawals=sum(s.early_withdrawals for s in timeline),
        currency=params.currency,
    )

