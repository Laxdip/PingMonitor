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
