---
title: Pathological
tags: [test, "quoted, with comma"]
nested:
  key: value
---

# Pathological

A 200-character unbroken token: zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz — it must be conserved, not dropped.

A very long bare URL that would eat the entire display: https://example.com/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/index.html?query=1&other=2#fragment

An aliased link [with text](https://example.com/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/segment/index.html?query=1&other=2#fragment) and a short one <https://x.example/a>.

- depth 0
  - depth 1
    - depth 2
      - depth 3
        - depth 4
          - depth 5
            - depth 6
              - depth 7

| a | b |
|---|---|
| 1 | 2 | 3 |
| only-one |

```
no language, and a line that is far too wide for a 256 pixel circular panel at any legible size
```

	indented code block
	second line

Setext heading
==============

Text with a hard break at the end,  
and the line after it.

Escapes: \*not bold\* and \`not code\`, plus a\*mid\*word.

Empty callout:

> [!ABSTRACT]

A paragraph that arrives with CRLF line endings,
as notes synced from Windows do.

Trailing whitespace and a final line with no newline at EOF.