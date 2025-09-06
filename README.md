# Rosie

Local-first CLI "maid" for safe Windows cleanup and organization.

## Getting Started

1. Create a virtual environment (Python 3.11+):

   python -m venv .venv
   . .venv/bin/activate  # Windows: .venv\\Scripts\\activate

2. Install (dev extras optional):

   pip install -e .[dev]

3. Run the CLI:

   python -m cli.main --help

   rosie scan <path> --out plan.json

Safety defaults: dry-run by default, no network, structured logs only.
