import json
from dataclasses import dataclass
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services.simulation import SimulationParameters, run_simulation, ModelBehavior

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def currency(value: float, currency_type: str = "USD") -> str:
    symbol = "R" if currency_type == "ZAR" else "$"
    try:
        return f"{symbol}{float(value):,.2f}"
    except:
        return str(value)

def integer(value: any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except:
        return str(value)

templates.env.filters["currency"] = currency
templates.env.filters["integer"] = integer


@dataclass
class CaseStudy:
    id: str
    title: str
    subtitle: str
    overview_html: str
    history_html: str
    params: SimulationParameters


CASE_STUDIES = {
    "classic": CaseStudy(
        id="classic",
        title="The Classic Ponzi",
        subtitle="Slow, steady, and mathematically doomed.",
        overview_html="""
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        Named after Charles Ponzi, this classic model relies on a low, steady influx of new investors to pay out earlier ones. The promised returns are high enough to attract money, but realistic enough not to immediately collapse the system.
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        However, because no real value is being generated, the system requires an ever-expanding base of recruits. Watch how the liquidity pool slowly drains as the payout obligations mount, culminating in a sudden liquidity crisis when new recruitment slows down.
        </p>
        """,
        history_html="""
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        In 1919, Charles Ponzi realized he could buy international reply coupons in countries with weak currencies (like Italy) and redeem them in the US for a profit. However, the logistics of actually buying and redeeming the coupons was impossible at scale.
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        Instead of stopping, Ponzi began taking money from new investors to pay off previous ones, promising a 50% return in 45 days. 
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        The model shows how steady exponential growth can mask insolvency for months, but eventually collapses once the required new investor volume exceeds the local population.
        </p>
        """,
        params=SimulationParameters(
            initial_participants=10,
            contribution_amount=1000.0,
            promised_return=1.5,
            recruitment_rate=1.2,
            recruitment_model="exponential",
            population_limit=50000,
            time_interval="month",
            max_periods=60,
            payout_delay=3,
            behavior=ModelBehavior(
                warmup_periods=9,  # Moderate grace period
                fomo_boost=1.5,
                concern_penalty=0.5,
                panic_penalty=0.05,
                concern_withdrawal_rate=0.02,
                panic_withdrawal_rate=0.15,
                churn_enabled=True,
                soft_cap_floor=0.05,
                volatility=0.1,
                shock_probability=0.02
            )
        )
    ),
    "madoff": CaseStudy(
        id="madoff",
        title="Madoff Wealth Management",
        subtitle="The longest-running Ponzi scheme in history.",
        overview_html="""
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        Bernie Madoff's scheme was the largest Ponzi scheme in history, worth an estimated $64.8 billion. Unlike flash-in-the-pan systems, Madoff's operation went undetected for decades because of its moderate promised returns.
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        Because Madoff only promised a modest 10–12% annual return, the drain on the cash pool was very slow. Supported by wealthy, exclusive investors who kept their money locked up for years, the scheme survived for over 30 years.
        </p>
        """,
        history_html="""
        <h4 class="text-xs font-bold uppercase tracking-wider text-white mb-2">The Moderate Return Strategy</h4>
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        Madoff claimed to use a "split-strike conversion" strategy, buying blue-chip stocks and limiting downside risk with options. In reality, he deposited all investor funds into a single Chase bank account and paid withdrawals out of that pool. 
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        The scheme collapsed only when the 2008 financial crisis triggered massive, simultaneous withdrawal requests that exceeded the incoming capital.
        </p>
        """,
        params=SimulationParameters(
            initial_participants=50,
            contribution_amount=50000.0,
            promised_return=1.10,
            recruitment_rate=1.15,
            recruitment_model="exponential",
            population_limit=5000,
            time_interval="year",
            max_periods=35,
            payout_delay=10,
            behavior=ModelBehavior(
                warmup_periods=6,        # Long 6-year grace period
                fomo_boost=1.1,          # Very subtle FOMO (exclusive)
                concern_penalty=0.8,     # Very loyal investors, slow to panic
                panic_penalty=0.2,
                concern_withdrawal_rate=0.01,
                panic_withdrawal_rate=0.05,
                churn_enabled=True,
                soft_cap_floor=0.1,      # Steady trickle of exclusive clients
                volatility=0.2,
                shock_probability=0.01
            )
        )
    ),
    "anchor": CaseStudy(
        id="anchor",
        title="Anchor Protocol Yield Reserve",
        subtitle="19.5% APY and the collapse of the Terra ecosystem.",
        overview_html="""
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        In 2021, the Terra blockchain ecosystem launched Anchor Protocol, promising depositors a flat 19.5% APY on their UST stablecoins. This rate was completely disconnected from the actual market demand for borrowing UST.
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        To maintain the 19.5% payout, the Terra founders had to repeatedly inject hundreds of millions of dollars into a "Yield Reserve" fund. As billions of UST flooded into Anchor, the Yield Reserve was drained at an exponential pace.
        </p>
        """,
        history_html="""
        <h4 class="text-xs font-bold uppercase tracking-wider text-white mb-2">The Subsidized Death Spiral</h4>
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        Once the reserve got dangerously close to zero, depositors realized the high yields were ending. 
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        A massive run on the bank occurred as users tried to withdraw their capital at once, breaking the stablecoin peg and vaporizing $40 billion of value in days.
        </p>
        """,
        params=SimulationParameters(
            initial_participants=50,
            contribution_amount=5000.0,
            promised_return=1.195,
            recruitment_rate=1.6,
            recruitment_model="exponential",
            payout_model="yield",
            population_limit=5000,
            time_interval="month",
            max_periods=24,
            payout_delay=2,
            behavior=ModelBehavior(
                warmup_periods=6,
                fomo_boost=1.5,
                concern_penalty=0.5,
                panic_penalty=0.05,
                concern_withdrawal_rate=0.03,
                panic_withdrawal_rate=0.20,  # Huge bank run
                churn_enabled=True,
                soft_cap_floor=0.05,
                volatility=0.15,
                shock_probability=0.05
            )
        )
    ),
    "loom": CaseStudy(
        id="loom",
        title="The Blessing Loom Game",
        subtitle="Hyper-viral social media circles.",
        overview_html="""
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        The "Blessing Loom" (or "Gifting Circle") is a modern pyramid scheme that spreads rapidly via social media platforms. It relies on game mechanics and psychological manipulation, framing the entry fee as a "gift".
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        The scheme uses a circular board. Eight people in the outer circle pay $100 to the person in the center ("the sun"). Once the outer ring fills, the circle splits into two new looms, and everyone moves one ring closer to the center.
        </p>
        """,
        history_html="""
        <h4 class="text-xs font-bold uppercase tracking-wider text-white mb-2">The Loom Geometry</h4>
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        For one person to get paid, they need 8 new recruits. For those 8 to get paid, they need 64 new recruits. 
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        This hyper-velocity exponential expansion runs out of local participants in a few weeks, leading to immediate collapse where 88% of participants lose their money.
        </p>
        """,
        params=SimulationParameters(
            initial_participants=1,
            contribution_amount=100.0,
            promised_return=8.0,
            recruitment_rate=8.0,
            recruitment_model="exponential",
            population_limit=1000,
            time_interval="week",
            max_periods=10,
            payout_delay=1,
            behavior=ModelBehavior(
                warmup_periods=10,           # Let the math kill it, not early panic
                fomo_boost=2.0,             # Hyper viral
                concern_penalty=0.1,        # Dead stop if it stalls
                panic_penalty=0.0,
                concern_withdrawal_rate=0.05,
                panic_withdrawal_rate=0.30,
                churn_enabled=False,        # One-shot, you don't "churn" back in
                soft_cap_floor=0.0,         # Hard cap
                volatility=0.3,
                shock_probability=0.0
            )
        )
    ),
    "crypto": CaseStudy(
        id="crypto",
        title="Hyper-Yield Crypto Farming",
        subtitle="10,000% APY and the fastest collapse in history.",
        overview_html="""
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        During the DeFi booms, "yield farms" offered astronomical returns paid in freshly minted tokens. This relies on hyper-viral marketing and massive upfront liquidity.
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        Because the recruitment rate is so high, the protocol quickly hits market saturation. The moment the influx of new capital stops, the massive daily payout obligations instantly wipe out the liquidity pool, resulting in a death spiral in a matter of days.
        </p>
        """,
        history_html="""
        <h4 class="text-xs font-bold uppercase tracking-wider text-white mb-2">DeFi Speculative Mechanics</h4>
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        Yield farming promised high interest by lending out assets. However, many projects simply paid yields by inflating their own token supply. 
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        Once the token price begins to fall, depositors withdraw and dump their tokens, accelerating the price drop and drying up all liquidity.
        </p>
        """,
        params=SimulationParameters(
            initial_participants=100,
            contribution_amount=500.0,
            promised_return=3.0,
            recruitment_rate=2.5,
            recruitment_model="saturating",
            payout_model="yield",
            population_limit=20000,
            time_interval="day",
            max_periods=30,
            payout_delay=2,
            behavior=ModelBehavior(
                warmup_periods=3,            # Very short grace period
                fomo_boost=1.8,
                concern_penalty=0.2,
                panic_penalty=0.01,
                concern_withdrawal_rate=0.05,
                panic_withdrawal_rate=0.25,  # Lightning fast bank run
                churn_enabled=True,
                soft_cap_floor=0.05,
                volatility=0.4,
                shock_probability=0.1
            )
        )
    ),
    "mlm": CaseStudy(
        id="mlm",
        title="Standard MLM Structure",
        subtitle="A slow bleed through market saturation.",
        overview_html="""
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        Multi-Level Marketing (MLM) structures often require upfront "inventory" purchases. While some have real products, the mathematical structure often mirrors a pyramid, heavily relying on recruitment.
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        Unlike a fast Ponzi, an MLM grows linearly or slowly saturates. The returns are lower, meaning the cash pool doesn't collapse overnight. Instead, the majority of participants at the bottom simply lose their money, while the system remains "technically" solvent for a long time.
        </p>
        """,
        history_html="""
        <h4 class="text-xs font-bold uppercase tracking-wider text-white mb-2">Retail Pyramid Structures</h4>
        <p class="text-sm text-zinc-300 leading-relaxed mb-4">
        MLMs incentive recruits to buy starter packs. Distributing commission upward ensures the top tiers profit while the vast majority (bottom 90%+) lose their capital due to market saturation.
        </p>
        <p class="text-sm text-zinc-300 leading-relaxed">
        The simulation highlights this stagnation: recruitment hits the population cap, the flow of new capital ceases, and the cash pool eventually trickles to zero.
        </p>
        """,
        params=SimulationParameters(
            initial_participants=5,
            contribution_amount=200.0,
            promised_return=1.1,
            recruitment_rate=3.0,
            recruitment_model="linear",
            population_limit=30000,
            time_interval="week",
            max_periods=104,
            payout_delay=4,
            behavior=ModelBehavior(
                warmup_periods=12,
                fomo_boost=1.2,
                concern_penalty=0.7,
                panic_penalty=0.1,
                concern_withdrawal_rate=0.01, # People rarely panic withdraw inventory
                panic_withdrawal_rate=0.02,
                churn_enabled=True,
                soft_cap_floor=0.05,
                volatility=0.1,
                shock_probability=0.01
            )
        )
    )
}

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, currency: str = "USD") -> HTMLResponse:
    # Default to classic
    return render_case_study(request, "classic", full_page=True, currency=currency)


@router.get("/models/{model_id}", response_class=HTMLResponse)
def load_model(request: Request, model_id: str, currency: str = "USD") -> HTMLResponse:
    is_htmx = request.headers.get("HX-Request") == "true"
    return render_case_study(request, model_id, full_page=not is_htmx, currency=currency)


@router.get("/models/{model_id}/history", response_class=HTMLResponse)
def load_model_history(request: Request, model_id: str) -> HTMLResponse:
    study = CASE_STUDIES.get(model_id)
    if not study:
        raise HTTPException(status_code=404, detail="Model not found")
    
    return templates.TemplateResponse(
        "history_page.html",
        {
            "request": request,
            "study": study,
        }
    )


def render_case_study(request: Request, model_id: str, full_page: bool, currency: str = "USD") -> HTMLResponse:
    study = CASE_STUDIES.get(model_id)
    if not study:
        raise HTTPException(status_code=404, detail="Model not found")

    # Override currency and apply scaling factor (1 USD = 18 ZAR)
    rate = 18.0 if currency == "ZAR" else 1.0
    sim_params = study.params.model_copy(update={
        "currency": currency,
        "contribution_amount": study.params.contribution_amount * rate
    })

    result = run_simulation(sim_params)
    
    # We will pass the full JSON timeline to the frontend to animate it
    context = {
        "request": request,
        "study": study,
        "studies": CASE_STUDIES.values(),
        "active_id": model_id,
        "full_page": full_page,
        "currency": currency,
        "currency_symbol": "R" if currency == "ZAR" else "$",
        "full_payload": json.dumps({
            "timeline": result["timeline"],
            "summary": result["summary"],
            "currency_symbol": "R" if currency == "ZAR" else "$"
        })
    }
    
    template = "index.html" if full_page else "partials/article.html"
    return templates.TemplateResponse(request, template, context)
