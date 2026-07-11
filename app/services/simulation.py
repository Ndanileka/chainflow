"""
ChainFlow Simulation Engine
============================

Architecture:
  BaseSimulator (universal rules) + ModelBehavior (per-scheme personality)

The base simulator handles ONLY the fundamental math:
  - Cash pool: inflows and outflows
  - Batch tracking: cohorts with contribution & payout schedule
  - Payout processing: pay matured batches if solvent
  - Collapse detection: can't cover a matured batch
  - Health ratio: cash_pool / upcoming_payouts

Each case study supplies a `ModelBehavior` that tunes:
  - Recruitment curve & sentiment response
  - Warmup grace period
  - Early withdrawal rates
  - Churn behavior
"""

from __future__ import annotations

from enum import Enum
from math import ceil, floor
import random

import polars as pl
from pydantic import BaseModel, Field, field_validator


# ─── Enums ──────────────────────────────────────────────────────────────────

class SentimentState(str, Enum):
    OPTIMISTIC = "optimistic"
    FOMO = "fomo"
    CONCERN = "concern"
    PANIC = "panic"
    COLLAPSED = "collapsed"


class RecruitmentModel(str, Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    SATURATING = "saturating"

class PayoutModel(str, Enum):
    LUMP_SUM = "lump_sum"
    YIELD = "yield"

# ─── Pydantic Models ────────────────────────────────────────────────────────

class ModelBehavior(BaseModel):
    """Per-scheme personality. Each case study defines one of these."""

    # Sentiment thresholds
    fomo_threshold: float = 3.0
    concern_threshold: float = 1.5
    panic_threshold: float = 0.8

    # Recruitment multipliers per sentiment state
    fomo_boost: float = 1.5
    concern_penalty: float = 0.5
    panic_penalty: float = 0.05

    # Early withdrawal rates
    concern_withdrawal_rate: float = 0.02
    panic_withdrawal_rate: float = 0.15

    # Warmup: periods before sentiment can go negative
    warmup_periods: int = 6

    # Churn: whether paid-out users free up capacity
    churn_enabled: bool = True

    # Soft cap floor: minimum recruitment trickle at 100% utilization
    soft_cap_floor: float = 0.05

    # Declining periods needed before CONCERN triggers from trend alone
    declining_periods_threshold: int = 3

    # Randomness (AI Magic)
    volatility: float = 0.0  # Gaussian noise (0.0 to 1.0)
    shock_probability: float = 0.0  # Chance per period of random FOMO/PANIC event


class SimulationParameters(BaseModel):
    """Input parameters for a single simulation run."""

    initial_participants: int = Field(ge=1)
    contribution_amount: float = Field(gt=0)
    promised_return: float = Field(ge=1.0)
    recruitment_rate: float = Field(ge=0)
    recruitment_model: RecruitmentModel = RecruitmentModel.EXPONENTIAL
    payout_model: PayoutModel = PayoutModel.LUMP_SUM
    population_limit: int = Field(ge=1)
    time_interval: str = "period"
    currency: str = "USD"
    max_periods: int = Field(ge=1, le=520, default=52)
    payout_delay: int = Field(ge=1, le=52, default=2)
    behavior: ModelBehavior = Field(default_factory=ModelBehavior)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v if v in {"USD", "ZAR"} else "USD"

    @field_validator("recruitment_model", mode="before")
    @classmethod
    def validate_recruitment_model(cls, v: str) -> str:
        if isinstance(v, str) and v in {"exponential", "linear", "saturating"}:
            return v
        return "exponential"


class TimelineState(BaseModel):
    """State snapshot for a single simulation period."""

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
    sentiment: str
    health_ratio: float
    inflow: float
    outflow: float
    peak_cash_pool: float
    early_withdrawals: int


class SimulationSummary(BaseModel):
    """End-of-simulation summary statistics."""

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


# ─── Internal Components ────────────────────────────────────────────────────

class ParticipantBatch:
    """A cohort of participants who joined in the same period."""

    __slots__ = ("period", "count", "contribution", "payout_due_period",
                 "payout_per_participant", "paid")

    def __init__(self, period: int, count: int, contribution: float,
                 payout_due_period: int, payout_per_participant: float) -> None:
        self.period = period
        self.count = count
        self.contribution = contribution
        self.payout_due_period = payout_due_period
        self.payout_per_participant = payout_per_participant
        self.paid = False

    def get_payout_due(self, period: int, payout_model: PayoutModel) -> float:
        if payout_model == PayoutModel.LUMP_SUM:
            if not self.paid and self.payout_due_period == period:
                return self.count * self.payout_per_participant
        elif payout_model == PayoutModel.YIELD:
            if not self.paid and period > self.period:
                return self.count * self.payout_per_participant
        return 0.0


class CashPool:
    """Tracks the central cash balance, total inflows and outflows."""

    __slots__ = ("balance", "total_contributions", "total_payouts")

    def __init__(self) -> None:
        self.balance = 0.0
        self.total_contributions = 0.0
        self.total_payouts = 0.0

    def contribute(self, amount: float) -> None:
        self.balance += amount
        self.total_contributions += amount

    def pay_due_batches(self, batches: list[ParticipantBatch], period: int, payout_model: PayoutModel) -> int:
        profitable = 0
        for batch in batches:
            amount_due = batch.get_payout_due(period, payout_model)
            if amount_due <= 0:
                continue
            if self.balance < amount_due:
                continue
            self.balance -= amount_due
            self.total_payouts += amount_due
            
            if payout_model == PayoutModel.LUMP_SUM:
                batch.paid = True
                profitable += batch.count
            elif payout_model == PayoutModel.YIELD:
                profitable += batch.count # They got their yield this period
                
        return profitable

    def process_early_withdrawals(self, amount: float) -> float:
        actual = min(amount, self.balance)
        self.balance -= actual
        self.total_payouts += actual
        return actual


class SentimentEngine:
    """
    Determines the psychological state of the market.
    All thresholds and multipliers come from ModelBehavior — nothing is hardcoded.
    """

    def __init__(self, behavior: ModelBehavior) -> None:
        self.b = behavior
        self.state = SentimentState.OPTIMISTIC
        self.declining_periods = 0
        self.previous_cash_pool = 0.0

    def evaluate(self, cash_pool: float, upcoming_payouts: float, period: int) -> SentimentState:
        health_ratio = cash_pool / upcoming_payouts if upcoming_payouts > 0 else 999.0

        # Grace period: don't penalize early-stage schemes
        if period < self.b.warmup_periods:
            self.previous_cash_pool = cash_pool
            self.state = (
                SentimentState.FOMO
                if health_ratio >= self.b.fomo_threshold
                else SentimentState.OPTIMISTIC
            )
            return self.state

        # Track trend
        if cash_pool < self.previous_cash_pool:
            self.declining_periods += 1
        else:
            self.declining_periods = 0
        self.previous_cash_pool = cash_pool

        # State transitions
        if health_ratio >= self.b.fomo_threshold and self.declining_periods == 0:
            self.state = SentimentState.FOMO
        elif health_ratio >= self.b.concern_threshold:
            if self.declining_periods >= self.b.declining_periods_threshold:
                self.state = SentimentState.CONCERN
            elif self.state == SentimentState.CONCERN:
                self.state = SentimentState.CONCERN  # hysteresis
            else:
                self.state = SentimentState.OPTIMISTIC
        elif health_ratio >= self.b.panic_threshold:
            self.state = SentimentState.CONCERN
        else:
            self.state = SentimentState.PANIC

        return self.state

    def get_recruitment_multiplier(self) -> float:
        if self.state == SentimentState.FOMO:
            return self.b.fomo_boost
        elif self.state == SentimentState.CONCERN:
            return self.b.concern_penalty
        elif self.state == SentimentState.PANIC:
            return self.b.panic_penalty
        return 1.0

    def get_early_withdrawal_rate(self) -> float:
        if self.state == SentimentState.CONCERN:
            return self.b.concern_withdrawal_rate
        elif self.state == SentimentState.PANIC:
            return self.b.panic_withdrawal_rate
        return 0.0


class Recruitment:
    """
    Calculates new recruits per period.
    Recruitment model math + soft saturation + sentiment multiplier.
    """

    def __init__(self, params: SimulationParameters) -> None:
        self.params = params

    def next_count(
        self,
        previous_new: int,
        active_participants: int,
        period: int,
        sentiment_multiplier: float = 1.0,
    ) -> int:
        pop_limit = self.params.population_limit
        b = self.params.behavior

        # Soft saturation: linear decay with a configurable floor
        utilization = min(1.0, active_participants / pop_limit) if pop_limit > 0 else 1.0
        soft_capacity = max(b.soft_cap_floor, 1.0 - (utilization * (1.0 - b.soft_cap_floor)))

        # Base recruitment (model-specific)
        model = self.params.recruitment_model
        
        # If previous_new dropped to 0, use 1 as a spark so the scheme can recover 
        # if sentiment improves. Otherwise, exponential models hard-lock at 0 forever.
        effective_previous = max(1, previous_new)
        
        if model == RecruitmentModel.LINEAR:
            projected = self.params.initial_participants * self.params.recruitment_rate
        elif model == RecruitmentModel.SATURATING:
            saturation = max(0.0, (pop_limit - active_participants) / pop_limit)
            projected = effective_previous * self.params.recruitment_rate * saturation
        else:  # EXPONENTIAL
            projected = effective_previous * self.params.recruitment_rate

        # Apply soft saturation + sentiment
        projected *= soft_capacity * sentiment_multiplier

        if period > 1 and projected > 0:
            projected = max(1, projected)

        return max(0, floor(projected))


# ─── Base Simulator ─────────────────────────────────────────────────────────

class BaseSimulator:
    """
    The plain, fundamental simulator. Handles universal rules only.
    All model-specific behavior comes from SimulationParameters.behavior.
    """

    def __init__(self, params: SimulationParameters) -> None:
        self.params = params
        self.recruitment = Recruitment(params)
        self.cash_pool = CashPool()
        self.batches: list[ParticipantBatch] = []
        self.profitable_participants = 0
        self.collapse_period: int | None = None
        self.sentiment_engine = SentimentEngine(params.behavior)
        self.peak_cash_pool = 0.0
        self.peak_period: int | None = None
        self.total_early_withdrawals = 0

    def run(self) -> list[TimelineState]:
        states: list[TimelineState] = []
        total_participants = 0
        active_participants = 0
        previous_new = self.params.initial_participants

        for period in range(self.params.max_periods + 1):
            # Apply Random Market Shocks
            forced_sentiment = None
            if period > 0 and self.params.behavior.shock_probability > 0:
                if random.random() < self.params.behavior.shock_probability:
                    forced_sentiment = random.choice([SentimentState.FOMO, SentimentState.PANIC])

            # 1. Upcoming payouts (lookahead)
            upcoming_payouts = sum(
                batch.get_payout_due(period + 1, self.params.payout_model)
                for batch in self.batches
            )

            # 2. Evaluate sentiment
            if forced_sentiment:
                sentiment = forced_sentiment
                self.sentiment_engine.state = forced_sentiment
            else:
                sentiment = self.sentiment_engine.evaluate(
                    self.cash_pool.balance, upcoming_payouts, period
                )
            recruit_mult = self.sentiment_engine.get_recruitment_multiplier()

            # 3. Recruit (sentiment-adjusted, active-based + stochastic noise)
            new_participants = (
                self.params.initial_participants
                if period == 0
                else self.recruitment.next_count(
                    previous_new, active_participants, period, recruit_mult
                )
            )
            
            # Apply noise to recruitment
            if period > 0 and self.params.behavior.volatility > 0:
                noise = max(0.1, random.gauss(1.0, self.params.behavior.volatility))
                new_participants = max(0, int(new_participants * noise))

            total_participants += new_participants
            active_participants += new_participants
            previous_new = new_participants

            # 4. Inflows (Stochastic contributions)
            contribution_mult = 1.0
            if self.params.behavior.volatility > 0:
                contribution_mult = max(0.1, random.gauss(1.0, self.params.behavior.volatility))
            
            actual_contribution = self.params.contribution_amount * contribution_mult
            inflow = new_participants * actual_contribution
            
            if new_participants > 0:
                self.cash_pool.contribute(inflow)
                
                # Calculate what they are owed per person
                if self.params.payout_model == PayoutModel.LUMP_SUM:
                    payout_per = ceil(actual_contribution * self.params.promised_return)
                else: # YIELD
                    # For yield, promised_return is 1.0X (e.g. 1.05 = 5% yield per period)
                    payout_per = actual_contribution * (self.params.promised_return - 1.0)
                    
                self.batches.append(ParticipantBatch(
                    period=period,
                    count=new_participants,
                    contribution=inflow,
                    payout_due_period=period + self.params.payout_delay,
                    payout_per_participant=payout_per,
                ))

            # 5. Stochastic early withdrawals
            early_withdrawal_rate = self.sentiment_engine.get_early_withdrawal_rate()
            early_withdrawals = 0
            if early_withdrawal_rate > 0 and period > 0:
                unpaid_immature = sum(
                    batch.count for batch in self.batches
                    if not batch.paid and batch.payout_due_period > period
                )
                early_withdrawals = int(unpaid_immature * early_withdrawal_rate)
                if early_withdrawals > 0:
                    self.cash_pool.process_early_withdrawals(
                        early_withdrawals * self.params.contribution_amount
                    )
                    self.total_early_withdrawals += early_withdrawals
                    if self.params.behavior.churn_enabled:
                        active_participants = max(0, active_participants - early_withdrawals)

            # 6. Required recruits to prevent collapse
            due_unpaid = sum(b.get_payout_due(period, self.params.payout_model) for b in self.batches)
            deficit = max(0.0, due_unpaid - self.cash_pool.balance)
            required_recruits = int(ceil(deficit / self.params.contribution_amount)) if deficit > 0 else 0

            # 7. Process scheduled payouts
            prev_payouts = self.cash_pool.total_payouts
            newly_paid = self.cash_pool.pay_due_batches(self.batches, period, self.params.payout_model)
            
            if self.params.payout_model == PayoutModel.LUMP_SUM:
                self.profitable_participants += newly_paid
            else:
                self.profitable_participants = max(self.profitable_participants, newly_paid) # Just track active yielders
                
            outflow = self.cash_pool.total_payouts - prev_payouts

            # Churn: paid-out participants leave (only for lump sum)
            if self.params.behavior.churn_enabled and self.params.payout_model == PayoutModel.LUMP_SUM:
                active_participants = max(0, active_participants - newly_paid)

            # 8. Track peak
            if self.cash_pool.balance > self.peak_cash_pool:
                self.peak_cash_pool = self.cash_pool.balance
                self.peak_period = period

            # 9. Health ratio
            health_ratio = (
                self.cash_pool.balance / upcoming_payouts
                if upcoming_payouts > 0 else 999.0
            )

            # 10. Collapse check
            # Pending payouts is just the future liability.
            if self.params.payout_model == PayoutModel.LUMP_SUM:
                pending_payouts = sum(
                    b.get_payout_due(b.payout_due_period, self.params.payout_model) for b in self.batches if not b.paid
                )
            else:
                pending_payouts = upcoming_payouts  # Yield has no 'end' maturity

            losing = total_participants - self.profitable_participants
            collapse = self._has_collapsed(period)

            if collapse and self.collapse_period is None:
                self.collapse_period = period
                sentiment = SentimentState.COLLAPSED

            states.append(TimelineState(
                period=period,
                label=f"{self.params.time_interval.title()} {period}",
                new_participants=new_participants,
                total_participants=total_participants,
                cash_pool=round(self.cash_pool.balance, 2),
                total_contributions=round(self.cash_pool.total_contributions, 2),
                total_payouts=round(self.cash_pool.total_payouts, 2),
                profitable_participants=self.profitable_participants,
                losing_participants=losing,
                pending_payouts=round(pending_payouts, 2),
                required_recruits=required_recruits,
                collapse=collapse,
                sentiment=sentiment.value,
                health_ratio=round(health_ratio, 2),
                inflow=round(inflow, 2),
                outflow=round(outflow, 2),
                peak_cash_pool=round(self.peak_cash_pool, 2),
                early_withdrawals=early_withdrawals,
            ))

            if collapse:
                break

        return states

    def _has_collapsed(self, period: int) -> bool:
        return any(
            self.cash_pool.balance < batch.get_payout_due(period, self.params.payout_model)
            for batch in self.batches
        )


# ─── Public API ─────────────────────────────────────────────────────────────

def run_simulation(params: SimulationParameters) -> dict[str, object]:
    sim = BaseSimulator(params)
    timeline = sim.run()
    summary = _summarize(timeline, params)

    return {
        "is_monte_carlo": False,
        "timeline": [state.model_dump() for state in timeline],
        "summary": summary.model_dump(),
    }


def run_monte_carlo(params: SimulationParameters, iterations: int = 500) -> dict[str, object]:
    """Run N simulations with Gaussian noise, aggregate results with Polars."""
    records: list[dict] = []

    for i in range(iterations):
        noisy = SimulationParameters(
            initial_participants=params.initial_participants,
            contribution_amount=max(0.01, random.gauss(
                params.contribution_amount, params.contribution_amount * 0.15
            )),
            promised_return=params.promised_return,
            recruitment_rate=max(0.0, random.gauss(
                params.recruitment_rate, params.recruitment_rate * 0.15
            )),
            recruitment_model=params.recruitment_model,
            population_limit=params.population_limit,
            time_interval=params.time_interval,
            currency=params.currency,
            max_periods=params.max_periods,
            payout_delay=params.payout_delay,
            behavior=params.behavior,
        )

        sim = BaseSimulator(noisy)
        timeline = sim.run()
        summary = _summarize(timeline, noisy)

        records.append({
            "iteration": i,
            "collapse_period": summary.collapse_period if summary.collapse_period is not None else params.max_periods,
            "max_cash_pool": max(s.cash_pool for s in timeline) if timeline else 0,
            "profitable_ratio": summary.profitable_participants / max(1, summary.total_participants),
        })

    # Aggregate with Polars
    df = pl.DataFrame(records)

    avg_collapse = df["collapse_period"].mean()
    avg_max_pool = df["max_cash_pool"].mean()
    avg_profitable = df["profitable_ratio"].mean() * 100
    survived = df.filter(pl.col("collapse_period") == params.max_periods).height

    # Build histogram
    hist = (
        df.group_by("collapse_period")
        .len()
        .sort("collapse_period")
    )

    hist_labels = []
    hist_data = []
    hist_map = dict(zip(
        hist["collapse_period"].to_list(),
        hist["len"].to_list(),
    ))
    for p in range(1, params.max_periods + 1):
        hist_labels.append(f"{params.time_interval.title()[:3]} {p}")
        hist_data.append(hist_map.get(p, 0))

    return {
        "is_monte_carlo": True,
        "iterations": iterations,
        "summary": {
            "avg_collapse_period": round(avg_collapse, 1),
            "avg_max_cash_pool": avg_max_pool,
            "avg_profitable_ratio": round(avg_profitable, 1),
            "survival_rate": round((survived / iterations) * 100, 1),
            "time_interval": params.time_interval,
            "currency": params.currency,
        },
        "histogram": {
            "labels": hist_labels,
            "data": hist_data,
        }
    }


def _summarize(timeline: list[TimelineState], params: SimulationParameters) -> SimulationSummary:
    last = timeline[-1]
    collapse_period = next((s.period for s in timeline if s.collapse), None)
    collapse_label = (
        f"{params.time_interval.title()} {collapse_period}"
        if collapse_period is not None
        else "No collapse within simulation"
    )
    sustainability = (
        last.total_contributions / last.pending_payouts
        if last.pending_payouts else 1.0
    )
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
        sustainability_ratio=round(sustainability, 2),
        peak_cash_pool=round(peak_state.cash_pool, 2),
        peak_period=peak_state.period,
        total_early_withdrawals=sum(s.early_withdrawals for s in timeline),
        currency=params.currency,
    )
