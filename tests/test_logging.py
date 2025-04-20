import os
import pytest
import logging
import re
from datetime import datetime
from unittest.mock import patch, MagicMock

import server  # This will trigger the logging setup

class TestLogging:
    """Tests for server logging functionality"""
    
    def test_log_directory_exists(self):
        """Test that the logs directory exists"""
        assert os.path.exists("logs"), "Logs directory does not exist"
    
    def test_log_file_creation(self):
        """Test that a log file is created with the correct naming pattern"""
        # Get all log files in the logs directory
        log_files = [f for f in os.listdir("logs") if f.startswith("server_") and f.endswith(".log")]
        
        # There should be at least one log file
        assert len(log_files) > 0, "No log files found in logs directory"
        
        # Check that at least one log file matches the expected pattern
        pattern = re.compile(r'server_\d{8}_\d{6}\.log')
        matching_files = [f for f in log_files if pattern.match(f)]
        assert len(matching_files) > 0, "No log files match the expected naming pattern"
    
    def test_logger_configuration(self):
        """Test that the logger is configured correctly"""
        # Get the logger instance
        logger = logging.getLogger("WebRTC-Server")
        
        # Check log level
        assert logger.level == logging.DEBUG, "Logger level should be DEBUG"
        
        # Check that there are at least two handlers (console and file)
        assert len(logger.handlers) >= 2, "Logger should have at least 2 handlers"
        
        # Check that one handler is a StreamHandler (console)
        assert any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) 
                   for h in logger.handlers), "Logger should have a StreamHandler"
        
        # Check that one handler is a FileHandler
        assert any(isinstance(h, logging.FileHandler) for h in logger.handlers), "Logger should have a FileHandler"
    
    def test_logging_output(self):
        """Test that logging messages are properly output"""
        with patch('logging.FileHandler.emit') as mock_emit:
            # Get the logger
            logger = logging.getLogger("WebRTC-Server")
            
            # Log a test message
            test_message = f"Test log message {datetime.now().isoformat()}"
            logger.info(test_message)
            
            # Check that emit was called
            mock_emit.assert_called()
            
            # Get the LogRecord from the call
            log_record = mock_emit.call_args[0][0]
            
            # Check that the message is correct
            assert log_record.getMessage() == test_message, "Log message is incorrect"
            
            # Check that the level is correct
            assert log_record.levelno == logging.INFO, "Log level is incorrect"
            
            # Check that the logger name is correct
            assert log_record.name == "WebRTC-Server", "Logger name is incorrect" 