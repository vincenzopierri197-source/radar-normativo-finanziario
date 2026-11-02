"""Entry point standalone del controllo giornaliero dei workflow."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from radar_normativo.monitor_workflows import main


if __name__ == "__main__":
    sys.exit(main())
