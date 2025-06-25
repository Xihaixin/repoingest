import json
import logging
from pathlib import Path
# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set logging level to INFO
    format='%(asctime)s - %(levelname)s - %(message)s',  # Set logging format
    handlers=[
        logging.FileHandler("gitingest.log", mode="w"),  # Log messages to the file gitingest.log
        logging.StreamHandler()  # Also output log messages to the console
    ]
)

class PathEncoder(json.JSONEncoder):
    def default(self, obj):
        # Handle Path object serialization
        if isinstance(obj, Path):
            return str(obj)  # Convert Path object to string
        
        # Use default serialization logic for other types
        return super().default(obj)