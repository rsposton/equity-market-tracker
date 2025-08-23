
# 🗂 Archive Guide for Direct Index + TLH Runs

To keep your project organized and make it easy to review past TLH cycles, use this folder and naming structure.

---

## 📂 Suggested Folder Structure
```
Project_Folder/
│
├── Rulebook/
│   └── DirectIndex_TLH_Rulebook.md
│
├── Templates/
│   ├── schwab_trade_file_template.csv
│   ├── wash_sale_unlocks_template.csv
│   └── TLH_Run_Checklist.md
│
├── Runs/
│   ├── 2025-08-22/               # Example run date
│   │   ├── positions_2025-08-22.csv
│   │   ├── transactions_2025-08-22.csv
│   │   ├── schwab_trade_file_2025-08-22.csv
│   │   ├── wash_sale_unlocks_2025-08-22.csv
│   │   └── turnover_summary_2025-08-22.md
│   ├── 2025-11-15/
│   │   ├── positions_2025-11-15.csv
│   │   ├── transactions_2025-11-15.csv
│   │   ├── schwab_trade_file_2025-11-15.csv
│   │   ├── wash_sale_unlocks_2025-11-15.csv
│   │   └── turnover_summary_2025-11-15.md
│   └── ...
│
└── README/
    └── DirectIndex_TLH_Project_README.md
```

---

## 📝 File Naming Conventions
- **positions_YYYY-MM-DD.csv** → positions snapshot on run date
- **transactions_YYYY-MM-DD.csv** → last 6 months transaction history
- **schwab_trade_file_YYYY-MM-DD.csv** → generated Schwab upload file
- **wash_sale_unlocks_YYYY-MM-DD.csv** → generated wash-sale calendar
- **turnover_summary_YYYY-MM-DD.md** → turnover % and order summary

---

## 📊 Why Archive Each Run?
- Keeps a permanent record of **what trades were suggested/executed**.
- Makes it easy to review **TLH effectiveness over time**.
- Provides documentation for **tax preparation** (realized losses and wash-sale compliance).

---

## 🔄 Workflow with Archiving
1. Before running TLH, create a new dated folder under `Runs/`.
2. Upload that day’s **positions** and **transactions** into the new folder.
3. After ChatGPT generates the outputs, save them into the same folder.
4. Optional: note any execution results or manual overrides in a simple README inside that run folder.

---

By following this structure, you’ll always be able to reconstruct **what decisions were made, when, and why**, which is crucial for tax reporting and performance analysis.
