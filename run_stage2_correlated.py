"""
run_stage2_correlated.py
--------------------------
STAGE 2: what actually happened. Same pool, same marginal default
probability per loan (so, on the rating agencies' own criteria, the SAME
rating) -- but now loans share exposure to one systemic factor (regional
housing market conditions) via a single-factor Gaussian copula. This is a
simplified version of the same model family used to price and rate real
CDOs pre-2008.

We sweep correlation (rho) and show:
  1. How the pool loss distribution grows a fat right tail as rho rises
  2. How P(AAA tranche loses money) and its VaR/Expected Shortfall explode
  3. A "Black Swan" stress scenario: what happens if the systemic factor
     actually realizes an extreme, crisis-level value instead of an
     average random draw

Run: python run_stage2_correlated.py
"""

import numpy as np
import pandas as pd

from src.pool import PoolParams, allocate_tranche_loss, CORRELATION_BENCHMARKS, ABX_AAA_PRICE_HISTORY
from src.simulate import (simulate_correlated_defaults, simulate_correlated_defaults_tcopula,
                          stressed_systemic_shock, stressed_systemic_shock_tcopula)
from src.metrics import (summarize, prob_any_loss, value_at_risk, expected_shortfall,
                          prob_negative_return, abx_price_to_implied_loss, implied_rho_for_target_loss)
from src.plotting import (
    plot_pool_loss_distribution,
    plot_aaa_loss_prob_vs_rho,
    plot_tail_metrics_vs_rho,
    plot_tranche_loss_distribution,
)

OUT_DIR = "results/figures"
N_TRIALS = 200_000
RHOS_FOR_SWEEP = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60]
RHOS_FOR_PLOT = [0.0, 0.15, 0.30, 0.50]  # subset shown in overlay histograms
RHOS_FOR_TCOPULA_CHECK = [0.15, 0.30, 0.50]


def main():
    params = PoolParams()
    struct = params.structure.as_dict()
    aaa_attach, aaa_detach = struct["Senior (AAA)"]
    aaa_coupon = params.structure.coupons()["Senior (AAA)"]

    print("=" * 70)
    print("STAGE 2 — Correlated defaults (single-factor t-copula)")
    print("=" * 70)
    print(f"Pool: {params.n_loans} loans | p(default)={params.p_default:.0%} "
          f"(UNCHANGED from Stage 1) | LGD={params.lgd:.0%} | trials={N_TRIALS:,}\n")

    # ---- sweep over rho ----
    sweep_rows = []
    pool_loss_by_rho = {}
    aaa_loss_by_rho = {}
    for rho in RHOS_FOR_SWEEP:
        pool_losses = simulate_correlated_defaults(
            n_loans=params.n_loans, p_default=params.p_default, lgd=params.lgd,
            rho=rho, n_trials=N_TRIALS, seed=42, lgd_sensitivity=params.lgd_sensitivity,
        )
        aaa_losses = allocate_tranche_loss(pool_losses, aaa_attach, aaa_detach)

        sweep_rows.append({
            "rho": rho,
            "AAA_prob_any_loss_%": 100 * prob_any_loss(aaa_losses),
            "AAA_VaR_99_%": 100 * value_at_risk(aaa_losses, 0.99),
            "AAA_ES_99_%": 100 * expected_shortfall(aaa_losses, 0.99),
            "pool_VaR_99_%": 100 * value_at_risk(pool_losses, 0.99),
            "AAA_mean_net_return_%": 100 * (aaa_coupon - aaa_losses.mean()),
            "AAA_prob_negative_return_%": 100 * prob_negative_return(aaa_losses, aaa_coupon),
        })

        if rho in RHOS_FOR_PLOT:
            pool_loss_by_rho[f"rho_{rho:.2f}"] = pool_losses
            aaa_loss_by_rho[f"rho_{rho:.2f}"] = aaa_losses

    sweep_df = pd.DataFrame(sweep_rows).round(4)
    print(sweep_df.to_string(index=False))
    sweep_df.to_csv("results/stage2_correlation_sweep.csv", index=False)

    # ---- figures ----
    plot_pool_loss_distribution(
        pool_loss_by_rho,
        subordination=aaa_attach,
        title="Stage 2: Pool loss distribution as default correlation rises\n"
              "(same marginal default probability, same rating, every time)",
        path=f"{OUT_DIR}/stage2_pool_loss_distribution_by_rho.png",
    )
    plot_tranche_loss_distribution(
        aaa_loss_by_rho, tranche_name="Senior (AAA)",
        title="AAA tranche loss distribution as correlation rises\n"
              "(rated AAA under all four scenarios)",
        path=f"{OUT_DIR}/stage2_aaa_loss_distribution_by_rho.png",
        xmax=100,
    )
    plot_aaa_loss_prob_vs_rho(
        sweep_df["rho"].values, sweep_df["AAA_prob_any_loss_%"].values / 100,
        path=f"{OUT_DIR}/stage2_aaa_loss_probability_vs_rho.png",
        benchmarks=CORRELATION_BENCHMARKS,
    )
    plot_tail_metrics_vs_rho(
        sweep_df["rho"].values, sweep_df["AAA_VaR_99_%"].values, sweep_df["AAA_ES_99_%"].values,
        path=f"{OUT_DIR}/stage2_tail_metrics_vs_rho.png",
        benchmarks=CORRELATION_BENCHMARKS,
    )

    zero_rho_prob = sweep_df.loc[sweep_df.rho == 0.0, "AAA_prob_any_loss_%"].values[0]
    high_rho_prob = sweep_df.loc[sweep_df.rho == 0.5, "AAA_prob_any_loss_%"].values[0]
    print(f"\n>> P(AAA loses money) rises from {zero_rho_prob:.3f}% at rho=0 "
          f"to {high_rho_prob:.3f}% at rho=0.5.")
    print(">> No individual loan's default probability changed. No rating would have changed.")
    print(">> Only the CORRELATION assumption changed -- and that alone decides whether\n"
          "   'AAA' means 'essentially risk-free' or 'exposed to real tail risk'.\n")

    # ---- Black Swan stress scenario ----
    print("-" * 70)
    print("BONUS: Black Swan stress test — systemic factor at -3 sigma")
    print("-" * 70)
    rho_stress = 0.30
    stress_losses = stressed_systemic_shock(
        n_loans=params.n_loans, p_default=params.p_default, lgd=params.lgd,
        rho=rho_stress, shock_sigma=3.0, n_trials=N_TRIALS, seed=7,
        lgd_sensitivity=params.lgd_sensitivity,
    )
    stress_aaa = allocate_tranche_loss(stress_losses, aaa_attach, aaa_detach)
    stress_summary = summarize(stress_aaa, f"AAA tranche | rho={rho_stress}, shock=-3 sigma",
                                coupon=aaa_coupon)
    for k, v in stress_summary.items():
        print(f"  {k}: {v}")

    tcop_stress_losses = stressed_systemic_shock_tcopula(
        n_loans=params.n_loans, p_default=params.p_default, lgd=params.lgd,
        rho=rho_stress, shock_sigma=3.0, n_trials=N_TRIALS, nu=4.0, seed=7,
        lgd_sensitivity=params.lgd_sensitivity,
    )
    tcop_stress_aaa = allocate_tranche_loss(tcop_stress_losses, aaa_attach, aaa_detach)
    tcop_stress_summary = summarize(tcop_stress_aaa, f"AAA tranche | rho={rho_stress}, shock=-3 sigma (t-copula)",
                                     coupon=aaa_coupon)
    print()
    for k, v in tcop_stress_summary.items():
        print(f"  {k}: {v}")

    combined = dict(aaa_loss_by_rho)
    combined["stress"] = stress_aaa
    plot_tranche_loss_distribution(
        combined, tranche_name="Senior (AAA)",
        title="AAA tranche loss: correlated scenarios vs. an actual\n"
              "systemic shock (-3 sigma housing downturn)",
        path=f"{OUT_DIR}/stage2_stress_vs_correlated.png",
        xmax=100,
    )
    print(f"\n>> Under an actual systemic shock, the 'AAA' tranche's expected loss\n"
          f"   is {stress_summary['mean_loss_%']:.1f}% of its notional. "
          f"Figure saved to {OUT_DIR}/stage2_stress_vs_correlated.png\n")

    # ---- calibration against real-world reference points ----
    print("-" * 70)
    print("CALIBRATION: how does rho compare to real-world reference points?")
    print("-" * 70)
    for label, rho_ref in CORRELATION_BENCHMARKS.items():
        losses = simulate_correlated_defaults(
            n_loans=params.n_loans, p_default=params.p_default, lgd=params.lgd,
            rho=rho_ref, n_trials=N_TRIALS, seed=42, lgd_sensitivity=params.lgd_sensitivity)
        aaa_losses = allocate_tranche_loss(losses, aaa_attach, aaa_detach)
        print(f"  {label} (rho={rho_ref}): P(AAA loss>0) = {prob_any_loss(aaa_losses):.4%}")

    print("\n  ABX.HE AAA price -> implied loss -> implied rho (base-correlation style):")
    for label, price in ABX_AAA_PRICE_HISTORY.items():
        target = abx_price_to_implied_loss(price)
        try:
            rho_implied = implied_rho_for_target_loss(
                simulate_correlated_defaults, params, target, n_trials=50_000)
            print(f"    {label}: price={price} -> implied_loss={target:.3f} -> implied rho={rho_implied:.3f}")
        except ValueError:
            print(f"    {label}: price={price} -> implied_loss={target:.3f} "
                  f"-> UNREACHABLE by rho alone even at 0.95 (see note below)")

    print("\n  Note: if a target is unreachable by rho alone, that's not a solver bug --")
    print("  a single-factor copula's tail loss probability is structurally capped near")
    print("  the marginal default probability itself (p_default). Matching a higher")
    print("  ABX-implied loss requires ALSO raising p_default, not just correlation --")
    print("  i.e. agencies may have underpriced INDIVIDUAL default risk, not only correlation.\n")

    # ---- robustness check: does a genuinely fat-tailed copula change the story? ----
    print("-" * 70)
    print("ROBUSTNESS CHECK: Gaussian vs t-copula at the same rho")
    print("-" * 70)
    for rho in RHOS_FOR_TCOPULA_CHECK:
        gauss_losses = simulate_correlated_defaults(
            n_loans=params.n_loans, p_default=params.p_default, lgd=params.lgd,
            rho=rho, n_trials=N_TRIALS, seed=42, lgd_sensitivity=0.0)
        tcop_losses = simulate_correlated_defaults_tcopula(
            n_loans=params.n_loans, p_default=params.p_default, lgd=params.lgd,
            rho=rho, n_trials=N_TRIALS, nu=4.0, seed=42)
        gauss_aaa = allocate_tranche_loss(gauss_losses, aaa_attach, aaa_detach)
        tcop_aaa = allocate_tranche_loss(tcop_losses, aaa_attach, aaa_detach)
        print(f"  rho={rho}: Gaussian P(loss>0)={prob_any_loss(gauss_aaa):.3%}  "
              f"ES99={100*expected_shortfall(gauss_aaa,0.99):.2f}%   |   "
              f"t-copula P(loss>0)={prob_any_loss(tcop_aaa):.3%}  "
              f"ES99={100*expected_shortfall(tcop_aaa,0.99):.2f}%")

if __name__ == "__main__":
    main()