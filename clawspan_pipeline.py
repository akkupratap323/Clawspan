"""Backward-compatibility shim — delegates to voice.pipeline.

All logic now lives in the ``voice/`` package.  This file exists so that
``python clawspan_pipeline.py`` and any imports of
``clawspan_pipeline.run_pipeline`` keep working.
"""

import asyncio

from voice.pipeline import JarvisProcessor, run_pipeline  # noqa: F401  (class name preserved internally)

if __name__ == "__main__":
    asyncio.run(run_pipeline())
