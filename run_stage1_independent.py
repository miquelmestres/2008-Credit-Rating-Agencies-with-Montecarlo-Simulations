"""
run_stage1_independent.py
--------------------------
STAGE 1: what the rating agencies' math effectively assumed.

If every loan in the pool defaults independently of every other loan, the
law of large numbers keeps the pool-wide loss ratio tightly clustered
around its expected value. With a 1000-loan pool, a 10% default
probability and 60% loss-given-default, expected pool loss is ~6% --
comfortably inside a 20% AAA subordination cushion. Under this assumption,
the AAA tranche is, for all practical purposes, bulletproof. This script
proves that numerically and is the baseline everything in Stage 2 will be
compared against.

Run: python run_stage1_independent.py
"""

import numpy as np
import pandas as pd

from src.pool import PoolParams
from src.simulate import simulate_independent_defaults
from src.metrics import summarize
from src.pool import allocate_tranche_loss
from src.plotting import plot_pool_loss_distribution

OUT_DIR = "results/figures"
N_TRIALS = 200_000


def main():
    params = PoolParams()
    struct = params.structure.as_dict()

    pool_losses = simulate_independent_defaults(
        n_loans=params.n_loans,
        p_default=params.p_default,
        lgd=params.lgd,
        n_trials=N_TRIALS,
    )

    print("=" * 70)
    print("STAGE 1 — Independent defaults (the agencies' implicit assumption)")
    print("=" * 70)
    print(f"Pool: {params.n_loans} loans | p(default)={params.p_default:.0%} | "
          f"LGD={params.lgd:.0%} | trials={N_TRIALS:,}\n")

    coupons = params.structure.coupons()
    rows = [summarize(pool_losses, "Pool (whole)")]
    for name, (attach, detach) in struct.items():
        tranche_losses = allocate_tranche_loss(pool_losses, attach, detach)
        rows.append(summarize(tranche_losses, f"{name} tranche", coupon=coupons[name]))

    df = pd.DataFrame(rows).set_index("scenario").round(4)
    print(df.to_string())
    df.to_csv("results/stage1_summary.csv")

    plot_pool_loss_distribution(
        {"rho_0.00": pool_losses},
        subordination=struct["Senior (AAA)"][0],
        title="Stage 1: Pool loss distribution under INDEPENDENT defaults\n"
              "(law of large numbers keeps losses tightly clustered)",
        path=f"{OUT_DIR}/stage1_pool_loss_distribution.png",
    )

    aaa_attach, aaa_detach = struct["Senior (AAA)"]
    aaa_losses = allocate_tranche_loss(pool_losses, aaa_attach, aaa_detach)
    aaa_loss_prob = (aaa_losses > 0).mean()

    print(f"\n>> Under independence, P(AAA tranche loses ANY money) = {aaa_loss_prob:.4%}")
    print(">> This is why, on paper, the AAA rating looked essentially risk-free.")
    print(f">> Figure saved to {OUT_DIR}/stage1_pool_loss_distribution.png\n")


if __name__ == "__main__":
    main()
