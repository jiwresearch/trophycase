Trophy Case: athlete trophy rooms. Live at https://trophycase.fyi

## Daily game schedule
`data/puzzles.json` sets hand-picked puzzles: `"YYYY-MM-DD": {"id": "<room id>", "clues": [five strings], "team": "...", "college": "..."}`.
`team` and `college` are optional and choose which links the solved screen shows. Days not listed use the automatic pick.
Run `python3 tools/check_puzzles.py` before pushing. Athletes in the schedule are held out of the automatic pick, so push schedule changes late at night.

## Finished rooms
`data/curated.json` holds written stories and hand corrections for generated rooms, keyed by room id: `line`, `stories` (`[year, headline, text]`), `add` (extra awards), `set` (fix an award's years or count), `born`, `region`, `lat`, `lon`, `teams`, `era`. The wing builds never touch it. A finished room joins the automatic daily pick unless it is in the schedule.
