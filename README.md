# Mission

Repository: <https://github.com/VEROLAMONDO/mission>

Mission is a small Python helper library for normalizing mission checklist text,
tracking checklist completion, and calculating launch countdowns.

## Development

Run the test suite with:

```bash
python -m pytest
```

The launch countdown helper treats naive datetimes as UTC and clamps past launch
times to `0` minutes so callers do not report negative time remaining.
