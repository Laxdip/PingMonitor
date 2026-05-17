#!/usr/bin/env python3
"""
================================================================================
  ADVANCED PING MONITOR - Pro Network Diagnostics Tool
  Author  : Prasad
  Version : 2.0
  License : MIT
================================================================================
"""

import time
import json
import os
import csv
import sys
import socket
import statistics
import threading
import argparse
from datetime import datetime, timedelta
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from pythonping import ping as pyping
    PYTHONPING_AVAILABLE = True
except ImportError:
    PYTHONPING_AVAILABLE = False

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    COLOR = True
except ImportError:
    COLOR = False
    class _Dummy:
        def __getattr__(self, _): return ""
    Fore = Back = Style = _Dummy()
