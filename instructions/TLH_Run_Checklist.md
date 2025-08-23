
# 📋 Direct Index + TLH Run Checklist

Use this checklist each time you want to generate a new TLH run inside your ChatGPT project.

---

## 1. Prepare Files
- [ ] Export your **current positions** file from Schwab/Mariner
  - Format: CSV (same style as `MPEP-Positions-YYYY-MM-DD.csv`)
- [ ] Export your **last 6 months of transactions** file
  - Format: CSV (same style as `MPEP_XXX130_Transactions_YYYYMMDD.csv`)

---

## 2. Upload Files into Project
- [ ] Upload both CSVs into your ChatGPT project folder
- [ ] Confirm that both appear in the project file list

---

## 3. Trigger TLH Run
- [ ] Tell ChatGPT: *“Run TLH with today’s positions and transactions”*
- [ ] ChatGPT will:
  - Parse positions (find unrealized losses)
  - Parse transactions (track realized losses, wash-sale cooldowns)
  - Apply the rules in **DirectIndex_TLH_Rulebook.md**
  - Generate:
    - ✅ **Schwab Trade File** (with one-for-one Mariner-style trades)
    - ✅ **Wash-Sale Unlocks file** (updated with cooldown windows)
    - ✅ **Turnover summary** (ensuring cap ≤20% unless drawdown)

---

## 4. Review Outputs
- [ ] Open the generated **Schwab Trade File** (`schwab_trade_file.csv`)
- [ ] Confirm orders align with your expectations
- [ ] Open the updated **Wash-Sale Unlocks file** for compliance tracking

---

## 5. Execute (Optional)
- [ ] Upload **schwab_trade_file.csv** into Schwab for order entry
- [ ] Monitor fills / confirm execution

---

## Notes
- Turnover cap defaults to **20% of account MV** (routine runs), up to **60%** in market drawdowns, never exceeding **80% monthly**.
- ETF replacements use **sector-aware mapping** (QQQ, XLF, XLE, XLI, SCHX, FNDX). 
- All ETF orders are kept **unaggregated** (Mariner style) for clean tax accounting.
- Wash-sale rule enforced at **90 days** (stricter than IRS 31 days).
