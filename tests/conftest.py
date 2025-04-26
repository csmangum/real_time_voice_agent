import pytest
import logging

@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration before each test"""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    logging.basicConfig(level=logging.NOTSET)
    yield 