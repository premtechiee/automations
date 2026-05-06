# paper-trader-state

Auto-managed branch holding runtime state for the **Angel One Trader**
GitHub Actions workflow. Do not commit code here.

- `data/paper_trader_state.json` — open positions, cumulative P&L, history
- `data/paper_reports/` — daily performance reports

To reset state: run the workflow with `reset_paper_state=yes`.
