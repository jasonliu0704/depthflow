reference agent pulse system

feature

each image/scene auto detect the best motion 

smooth motion

high quality

eval comprehensively

sometimes generated video are distorted

There are also some practical limitations in the implementation details:

It explains decisions only with a few canned reason strings. That’s good for debugging, but not enough to understand borderline cases or tune thresholds confidently.
The thresholds are hard-coded. They are easy to work with, but they are not calibrated against a real evaluation set yet.
It chooses one of three fixed profiles rather than tuning motion continuously. So even a good classification still snaps to coarse presets instead of adapting offset/zoom strength more precisely.
The heuristic runs per image independently. That helps mixed batches, but it can make a stitched video feel less stylistically consistent if adjacent clips resolve to different modes.
It only reports clip_reports for mode=auto, so we don’t yet get comparable diagnostics for manually selected modes.
It falls back to tour on heuristic failure. That is safe operationally, but not always the safest visual fallback; for some architectural images, gentle would arguably be lower risk.

if needed train model
