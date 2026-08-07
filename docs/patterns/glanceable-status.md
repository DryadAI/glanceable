# Pattern: glanceable status

The most common HUD shape — a short piece of state the wearer reads in one
glance and then forgets.

## Rules

- **One idea per frame.** If it needs two sentences, it is not glanceable.
- **Front-load the noun.** "Rain in 20 min", not "In 20 minutes, rain".
- **No motion.** Do not blink, slide, or pulse to draw attention. Peripheral
  motion is pre-attentional and steals focus involuntarily.
- **Centre on the equator.** Widest chord, easiest saccade target.

## Sizing

Larger type is better for a single value; smaller type is only worth it when
the content genuinely needs the words. Ask the engine rather than guessing:

```python
for size in (24, 20, 16, 13):
    font = Font(path, size)
    layout = font.layout(message, HALO, max_lines=3)
    if not layout.truncated:
        break   # largest size that fits the whole message
```

This "shrink to fit" loop is the right default for status text, and it is
possible only because `truncated` is exposed rather than silently clipped.

## Anti-patterns

- Scrolling long text instead of shortening it.
- A progress bar that animates continuously in the wearer's periphery.
- Two competing values on one frame; pick the one that drives a decision.
