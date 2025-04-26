import unittest
import logging
from app.config.logging_config import configure_logging

class TestLoggingConfig(unittest.TestCase):
    def test_configure_logging(self):
        # Test that the function returns a logger
        logger = configure_logging()
        self.assertIsInstance(logger, logging.Logger)
        
        # Test that the logger has the correct name
        self.assertEqual(logger.name, "ac_server")
        
        # Test that the logger has the correct level
        self.assertEqual(logger.level, logging.INFO)
        
        # Test that the root logger has the correct format
        root_logger = logging.getLogger()
        self.assertEqual(len(root_logger.handlers), 1)
        handler = root_logger.handlers[0]
        self.assertIsInstance(handler, logging.StreamHandler)
        formatter = handler.formatter
        self.assertEqual(formatter._fmt, "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.assertEqual(formatter.datefmt, "%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    unittest.main() 