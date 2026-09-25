import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from export_dataset import eligible_groups


def test_release_requires_four_distinct_eligible_views():
    rows = [
        {
            "target_cell": "q",
            "representation": rep,
            "training_eligible": True,
            "mapping_status": "matched",
        }
        for rep in ("sog", "aig", "aimg", "xag")
    ]
    assert set(eligible_groups(pd.DataFrame(rows))) == {"q"}
    assert not eligible_groups(pd.DataFrame(rows[:3]))
    rows[3]["representation"] = "aig"
    assert not eligible_groups(pd.DataFrame(rows))
    rows[3]["representation"] = "xag"
    rows[3]["training_eligible"] = False
    assert not eligible_groups(pd.DataFrame(rows))
