# 📑 Direct Index + TLH Rulebook

## 🎯 Core Objective

-   Track the **S&P 500** closely, while excluding:
    -   All **pharma/biotech/healthcare single stocks** (to avoid FDA
        COI).
    -   All **tobacco/nicotine producers** (ethical preference).
-   Improve **after-tax performance** via **systematic tax-loss
    harvesting (TLH)** while minimizing tracking error.

------------------------------------------------------------------------

## 🚫 Exclusion Rules

-   **No buys** of:
    -   Pharma/biotech/healthcare single names.
    -   Tobacco/nicotine producers.
-   Existing holdings in these groups are **eligible TLH sells**, but
    **not repurchased** later.

------------------------------------------------------------------------

## 🔄 Replacement Rules (with Sector-Aware Mapping)

-   **Default ETF for replacements:** **SCHX** (broad U.S. large-cap).
-   **Sector-aware replacements (style-sensitive):**

  --------------------------------------------------------------------------
  Sector / Stock Type               ETF Replacement            Notes
  --------------------------------- -------------------------- -------------
  **Tech / Mega-cap Growth** (AAPL, **QQQ** or **VUG**         Preserves
  MSFT, NVDA, GOOG, META, TSLA,                                growth tilt
  AMZN, etc.)                                                  

  **Financials / Banks** (JPM, BAC, **XLF**                    Maintains
  C, GS, MS, etc.)                                             financials
                                                               exposure

  **Energy** (XOM, CVX, SLB, etc.)  **XLE**                    Maintains
                                                               energy sector

  **Industrials** (CAT, BA, HON,    **XLI**                    Maintains
  UNP, etc.)                                                   industrials
                                                               exposure

  **General / Other**               **SCHX**                   Default broad
                                                               replacement

  **Value Tilt (optional)**         **FNDX**                   Use if style
  (consumer staples, old-economy                               rebalance
  names)                                                       needed

  **Healthcare / Pharma / Biotech** **SCHX**                   🚫 COI
                                                               exclusion, no
                                                               rotation back

  **Tobacco / Nicotine**            **SCHX**                   🚫 Values
                                                               exclusion, no
                                                               rotation back
  --------------------------------------------------------------------------

-   **ETF share quantity must be based on current market price** (live
    lookup at trade generation, e.g., SCHX \$25.54 today).

------------------------------------------------------------------------

## 📉 Tax-Loss Harvesting (TLH) Triggers

-   **Primary trigger:** unrealized loss ≥ **--8%** and ≥ **\$25**.
-   **Opportunistic trigger:** if S&P 500 drops ≥ **5--7% in a week**,
    lower threshold to --5%.

------------------------------------------------------------------------

## 🔒 Wash-Sale / Cooldown Rules

-   **No repurchase** of a sold stock within **≥90 days**.
-   Proceeds sit in replacement ETF during cooldown.
-   **Rotation-back allowed** once cooldown ends, unless the stock is
    excluded.

------------------------------------------------------------------------

## 💸 Turnover Controls

-   **Normal run:** ≤20% of account MV.
-   **Drawdown mode:** up to 60%.
-   **Monthly hard cap:** 80%.

------------------------------------------------------------------------

## 📊 Rebalancing Rules

-   Rebalance with ETFs if **sector/style drift \>0.5%**.
-   **Capital gains budget:** ≤2% of portfolio annually.

------------------------------------------------------------------------

## 📆 Process

1.  **Monthly light scan** --- check losses, wash-sale calendar.
2.  **Quarterly TLH run** --- generate **SELL stock → BUY ETF** orders,
    plus **SELL ETF → BUY stock** rotation orders.
3.  **Annual review** --- drift vs. S&P 500, COI check, gains/losses
    summary.

------------------------------------------------------------------------

## 🧾 Trade File Format

-   Follow **Mariner-style one-for-one pairing**:
    -   Each harvested stock has its own ETF buy order.
    -   Each rotation-back has its own ETF sell order.
-   **Do not aggregate ETF orders**; keep them itemized for tax
    accounting clarity.
