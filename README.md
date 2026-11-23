Trophy Case: athlete trophy rooms. Live at https://trophycase.fyi

## Daily game schedule
`data/puzzles.json` sets hand-picked puzzles: `"YYYY-MM-DD": {"id": "<room id>", "clues": [five strings], "team": "...", "college": "..."}`.
`team` and `college` are optional and choose which links the solved screen shows. Days not listed use the automatic pick.
Run `python3 tools/check_puzzles.py` before pushing. Athletes in the schedule are held out of the automatic pick, so push schedule changes late at night.
