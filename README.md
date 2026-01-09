
# 📂 Direct Index + TLH Project README

This project folder contains everything needed to manage your **Direct Index + Tax-Loss Harvesting (TLH) strategy**.

---

## 📑 Core Files

### 1. **DirectIndex_TLH_Rulebook.md**
- The "source of truth" for your strategy.
- Documents your objectives, exclusion rules, ETF replacement mapping, TLH triggers, wash-sale rules, turnover caps, and process.
- Update this file whenever you change your rules (e.g., add new sector ETFs, change thresholds).

### 2. **schwab_trade_file_template.csv**
- Blank template showing the correct Schwab trade file format.
- Each TLH run generates a filled version (`schwab_trade_file.csv`), which you can upload into Schwab.
- Trades are **Mariner-style one-for-one** (stock sells paired with ETF buys, ETF sells paired with stock buys).

### 3. **wash_sale_unlocks_template.csv**
- Blank template for wash-sale cooldown tracking.
- Each TLH run generates a filled version (`wash_sale_unlocks.csv`) showing earliest re-entry dates for harvested names.
- Enforces your **90-day wash-sale rule** (stricter than IRS 31 days).

### 4. **TLH_Run_Checklist.md**
- Step-by-step workflow for each TLH cycle.
- Ensures you always remember to:
  - Export positions and transactions
  - Upload into ChatGPT project
  - Generate trades + wash-sale calendar
  - Review turnover summary and compliance
  - Upload to Schwab (optional)

---

## 🔄 Workflow Summary

1. **Prepare data**
   - Export **positions CSV** and **transactions CSV** from Schwab/Mariner.

2. **Upload to ChatGPT Project**
   - Place both files into this project folder.

3. **Run TLH**
   - Tell ChatGPT: *“Run TLH with today’s positions and transactions.”*
   - ChatGPT will:
     - Apply rules from **DirectIndex_TLH_Rulebook.md**
     - Generate **schwab_trade_file.csv**
     - Generate **wash_sale_unlocks.csv**
     - Produce a **turnover summary**

4. **Review & Execute**
   - Check the trade file and wash-sale unlocks
   - Confirm turnover ≤20% (unless drawdown mode)
   - Upload `schwab_trade_file.csv` into Schwab to execute trades

---

## ⚖️ Key Rules Embedded
- **Exclusions**: No pharma/biotech/healthcare single names (COI) or tobacco/nicotine.  
- **Replacements**: Sector-aware ETFs (QQQ, XLF, XLE, XLI, SCHX, FNDX).  
- **TLH Triggers**: Loss ≥8% and $25, or ≥5% during market drawdowns.  
- **Wash-Sale**: 90 days minimum before rotation back.  
- **Turnover**: 20% cap per run, 60% in drawdowns, 80% monthly hard cap.  
- **Style**: Mariner-style (unaggregated ETF trades).  

---

## 📝 Notes
- Keep all 4 template/guide files in this project so the workflow is always reproducible.
- Add each new **positions** and **transactions** CSV into the project before a run.
- After each run, you can archive the generated `schwab_trade_file.csv` and `wash_sale_unlocks.csv` for your records.

---

## ✅ Adding Validation Rules
Validation rules for lot-level data live in `ingestor.py` inside the `Lot` Pydantic model.

To add a new rule:
1. Open `ingestor.py` and find the `Lot` class.
2. Add a new field or `@validator` method to enforce the rule (for example, reject negative prices or enforce a minimum quantity).
3. Update or add tests in `tests/test_ingestor.py` to cover the new rule.
