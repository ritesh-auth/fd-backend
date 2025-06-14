import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


#Create log directory if not available
log_directory = Path("logs")
log_directory.mkdir(exist_ok=True)


#Setup logger for file and console
def _setup_logger(name: str = __name__, level: int = logging.INFO) -> logging.Logger:
    
    logger = logging.getLogger(name)

    if logger.hasHandlers():
        return logger
    
    logger.setLevel(level)

    #Setup the name format and date format for the fike
    formatter = logging.Formatter(
        fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt = '%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Ensure the log file's parent directory exists
    file_handler_path = log_directory / f"{name.replace('.', '_')}.log"
    file_handler_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=file_handler_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )

    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# function can be imported in other files to get logger instance
def get_logger(name: str = __name__) -> logging.Logger:
    """Get the logger instance"""
    return _setup_logger(name)

def _setup_uvicorn_logger():

    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")

    #Setup the name format and date format for the fike
    formatter = logging.Formatter(
        fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt = '%Y-%m-%d %H:%M:%S'
    )

    uvicorn_file_handler = RotatingFileHandler(
        filename=log_directory / ".log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )

    uvicorn_file_handler.setFormatter(formatter)

    uvicorn_logger.addHandler(uvicorn_file_handler)
    uvicorn_access_logger.addHandler(uvicorn_file_handler)


#App logger
app_logger = get_logger("fd-backend")
