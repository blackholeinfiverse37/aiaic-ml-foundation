"""Price FORECAST for AIAIC: a range for a future date, from information known on the day it is asked.

Separate from `src/training` and `/v1/predict` on purpose. That model reads the SAME day's min and max price to
predict the same day's modal price, so it describes a day that is already known; it cannot say anything about next
week. This package answers the question AIAIC asks: "on `as_of`, what range is the modal price likely to be in
`horizon_days` from now, and has this model beaten the simple rule 'the price stays where it is'?"

Rules every module here keeps (tests in `tests/forecast/` fail when one is broken):
- a feature for `as_of` uses only prices dated ON OR BEFORE `as_of`; never min/max, never the target day;
- lags are by DATE within ONE mandi (never "the previous row", which is another mandi on the same day);
- the answer is a range (p10, p50, p90), with its backtest beside it;
- a crop, state or mandi the model was not trained on is refused, never guessed.
"""
