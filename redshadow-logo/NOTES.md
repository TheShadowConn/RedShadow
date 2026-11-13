# RedShadow wordmark: round 1

## Files
- `redshadow-concepts-board.png`: comparison board for concepts A to E. Each concept is shown in colour, reversed, one colour, at true 16 px, and as an icon.
- `concepts/`: one SVG per concept, plus `-reversed`, `-mono` and `-icon` variants.
- `final/`: recommended direction **A, Redacted**.
  - `redshadow-wordmark-light.svg`: for light backgrounds.
  - `redshadow-wordmark-dark.svg`: for dark backgrounds. SHADOW is thinned about 3% to offset irradiation.
  - `redshadow-wordmark-black.svg`, `-white.svg`, `-red.svg`: one-colour versions.
  - `redshadow-icon.svg`: the icon. `redshadow-icon-small.svg` is a larger-R cut for 16 to 32 px.
  - `icons/`: favicon.ico (16/32/48), favicon.svg, PNG favicons, apple-touch-icon, 192/512 and maskable icons, app-icon SVG (red tile on ink), site.webmanifest, and `head-snippet.html`.
- `src/build.py`: regenerates every SVG. It needs `skia-pathops` and `fonttools`. `src/board.py` rebuilds the board HTML.

## Type
- There is no font file. The letters are custom squared-geometric capitals built in code from rounded rectangles and 15° diagonals, and every output is outlines. This means there is no licence to clear and the letterforms are ownable.
- Metrics (units): cap height 100, vertical stem 20, horizontal bar 17 (optically thinner), outer corner radius 27, and diagonals at 15° in A, R and W. The middle bars sit at y=47, which is optically high.
- Optical corrections applied:
  - The S terminals stop at the end of the corner curve, so the S never closes into an 8.
  - Side bearings are set by side shape: straight, round, diagonal or open.
  - The icon R is nudged 2 units right to balance its open leg.
  - The dark version is thinned.
- For UI text next to the logo, use a neutral grotesk such as Inter or IBM Plex Sans (both OFL). Do not use this alphabet for body copy.

## Colour
| Role | HEX | RGB |
|---|---|---|
| Red (signal) | `#FF2A1A` | 255 42 26 |
| Ink | `#0A0A0B` | 10 10 11 |
| Paper | `#F1EFE8` | 241 239 232 |

- Red on paper and red on ink both pass for large graphics.
- Red text on white is about 3.6:1. That is fine for the logo but too low for small body text.
- The CMYK and Pantone matches still need a print proof.

## Tests run
- `svg_audit.py`: all files score 96 to 99/100, with no live text, strokes, filters or gradients.
  - The extra-wide aspect is flagged. The square icon covers small uses.
  - D (Cast) has a high anchor count from its approximate shadow offset. Rebuild it cleanly if D is chosen.
- `preview_sheet.py` covered the icons at 16 to 128 px, one colour and reversed. I checked all five rows by eye.
  - E's first horizontal split read as a battery, so the terminator is now 45°.
- Not done:
  - Trademark search. Use a professional search before adoption.
  - Print proof.
