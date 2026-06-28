import os
import time
import yaml
import json
import re
import random
import requests
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Tuple


# --- PATH RESOLUTION & ENV SETUP ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)
