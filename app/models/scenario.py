from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="Untitled scenario")
    initial_participants: Mapped[int] = mapped_column(Integer, default=10)
    contribution_amount: Mapped[float] = mapped_column(Float, default=100.0)
    promised_return: Mapped[float] = mapped_column(Float, default=1.5)
    recruitment_rate: Mapped[float] = mapped_column(Float, default=1.8)
    recruitment_model: Mapped[str] = mapped_column(String(40), default="exponential")
    population_limit: Mapped[int] = mapped_column(Integer, default=10000)
    time_interval: Mapped[str] = mapped_column(String(30), default="week")
    max_periods: Mapped[int] = mapped_column(Integer, default=52)
    payout_delay: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    results: Mapped[list["SimulationResult"]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
    )


class SimulationResult(Base):
    __tablename__ = "simulation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), index=True)
    timeline_json: Mapped[str] = mapped_column(Text)
    summary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scenario: Mapped[Scenario] = relationship(back_populates="results")
