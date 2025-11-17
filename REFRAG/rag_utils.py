#!/usr/bin/env python3
"""
rag_utils.py — Utility functions for RAG pipeline
"""

import sys
import logging
from functools import wraps
from time import sleep

# -----------------------
# Logging config
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("rag_prod")


# -----------------------
# Helpers: retry/backoff for API calls
# -----------------------
def retry(exceptions, tries=4, delay=1.0, backoff=2.0, logger=logger):
    """
    Decorator for retrying functions with exponential backoff.
    """
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    msg = f"{f.__name__} failed with {e}, retrying in {mdelay} seconds..."
                    logger.warning(msg)
                    sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            # last attempt
            return f(*args, **kwargs)
        return f_retry
    return deco_retry

