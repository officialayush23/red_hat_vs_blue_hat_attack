"""One-off diagnostic (2026-08-30): does PaddleOCRVL(use_queues=False) actually
reach the inner pipeline's use_queues attribute, or is it getting lost/
overridden by the separate 'engine_config' bucketing system? Prints every
place the attribute could plausibly live, no predict() call (so it can't hang).
Delete after use -- not part of the real codebase."""

from paddleocr import PaddleOCRVL

print("Constructing PaddleOCRVL(use_queues=False)...")
ocr = PaddleOCRVL(use_queues=False)

print("\n--- inspection ---")
print("ocr._params.get('use_queues'):", ocr._params.get("use_queues"))

pipe = ocr.paddlex_pipeline
print("type(ocr.paddlex_pipeline):", type(pipe))
print("hasattr use_queues directly:", hasattr(pipe, "use_queues"),
      getattr(pipe, "use_queues", "<none>"))

# If paddlex_pipeline is an auto-parallel wrapper, the real inner pipeline
# (the one with self.use_queues from pipeline.py) is usually stashed under
# one of these common attribute names -- check each without guessing blind.
for attr in ("_pipeline", "pipeline", "_inner_pipeline", "inner_pipeline"):
    inner = getattr(pipe, attr, None)
    if inner is not None:
        print(f"pipe.{attr} ->", type(inner), "| use_queues =",
              getattr(inner, "use_queues", "<no use_queues attr>"))

# Also print the merged config we THINK we built, straight from the wrapper.
print("\nocr._merged_paddlex_config.get('use_queues'):",
      ocr._merged_paddlex_config.get("use_queues", "<missing key>"))
