from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, floor
import random


@dataclass(frozen=True)
class SimulationParameters:
    initial_participants: int
    contribution_amount: float
    promised_return: float
    recruitment_rate: float
    recruitment_model: str
    population_limit: int
    time_interval: str
    max_periods: int = 52
    payout_delay: int = 2


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
    collapse: bool


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
            max_periods=normalized.max_periods,
            payout_delay=normalized.payout_delay,
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
            "time_interval": normalized.time_interval
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
        max_periods=max(1, min(520, int(params.max_periods))),
        payout_delay=max(1, min(52, int(params.payout_delay))),
    )


class Recruitment:
    def __init__(self, params: SimulationParameters) -> None:
        self.params = params

    def next_count(self, previous_new: int, total_participants: int, period: int) -> int:
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


class Timeline:
    def __init__(self, params: SimulationParameters) -> None:
        self.params = params
        self.recruitment = Recruitment(params)
        self.cash_pool = CashPool()
        self.batches: list[ParticipantBatch] = []
        self.profitable_participants = 0
        self.collapse_period: int | None = None

    def run(self) -> list[TimelineState]:
        states: list[TimelineState] = []
        total_participants = 0
        previous_new = self.params.initial_participants

        for period in range(self.params.max_periods + 1):
            new_participants = (
                self.params.initial_participants
                if period == 0
                else self.recruitment.next_count(previous_new, total_participants, period)
            )
            total_participants += new_participants
            previous_new = new_participants
            self._add_batch(period, new_participants)

            self.profitable_participants += self.cash_pool.pay_due_batches(
                self.batches,
                period,
            )

            pending_payouts = sum(
                batch.total_payout_due for batch in self.batches if not batch.paid
            )
            losing_participants = total_participants - self.profitable_participants
            collapse = self._has_collapsed(period, new_participants)
            if collapse and self.collapse_period is None:
                self.collapse_period = period

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
                    collapse=collapse,
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
        no_recruits_left = (
            new_participants == 0
            and period > 0
            and any(not batch.paid for batch in self.batches)
        )
        return cannot_pay_due or no_recruits_left


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
    )
