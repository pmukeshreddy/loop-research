# Pipeline diagram

[`synthetic-data-pipeline.png`](synthetic-data-pipeline.png) is rendered directly
from page 1 of the supplied [`synthetic-data-pipeline.pdf`](synthetic-data-pipeline.pdf),
originally attached as `synthetic_data_pipeline.pdf`. The source PDF is preserved
unchanged. No labels, arrows, shapes or revision loops were redrawn.

The PNG is 1012 × 1795 pixels at 400 dpi, rendered in grayscale with a white
background. The crop removes empty page margins, the figure caption and page
number, leaving a small margin around the complete diagram. The README displays
it at 420 pixels wide and links to the full-resolution image.

Reproduce from the repository root with Poppler:

```bash
pdftoppm -f 1 -singlefile -r 400 -gray \
  -x 1194 -y 366 -W 1012 -H 1795 -png \
  docs/assets/synthetic-data-pipeline.pdf docs/assets/synthetic-data-pipeline
```
