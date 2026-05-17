#!/usr/bin/env python3
"""
Professional Ping Monitor - Ye CLI Wala Haii🌝
Features: Continuous monitoring, statistics, logging, alerts
"""

import time
import json
import os
from datetime import datetime
from pythonping import ping
from colorama import init, Fore, Style
import threading
from collections import deque

# Initialize colorama for colored output
init(autoreset=True)

class PingMonitor:
    def __init__(self):
        self.results = []
        self.is_monitoring = False
        self.stats = {
            'sent': 0,
            'received': 0,
            'lost': 0,
            'min_rtt': float('inf'),
            'max_rtt': 0,
            'avg_rtt': 0,
            'rtts': []
        }
        self.alert_threshold = 100  # ms
        self.log_file = "ping_log.json"
        
    def print_banner(self):
        """Display professional banner"""
        banner = f"""
{Fore.CYAN}{'='*60}
{Fore.GREEN}🔍 PROFESSIONAL PING MONITOR v1.0
{Fore.YELLOW}📡 Real-time Network Monitoring Tool
{Fore.CYAN}{'='*60}{Style.RESET_ALL}
        """
        print(banner)
    
    def ping_host(self, host, count=1, timeout=2):
        """
        Send ping to host and return result
        """
        try:
            response = ping(host, count=count, timeout=timeout, verbose=False)
            
            if response.success():
                rtt = response.rtt_avg_ms
                return {
                    'success': True,
                    'rtt': round(rtt, 2),
                    'host': host,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'rtt': None,
                    'host': host,
                    'timestamp': datetime.now().isoformat(),
                    'error': 'Request timeout'
                }
        except Exception as e:
            return {
                'success': False,
                'rtt': None,
                'host': host,
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def update_statistics(self, result):
        """Update monitoring statistics"""
        self.stats['sent'] += 1
        
        if result['success']:
            self.stats['received'] += 1
            rtt = result['rtt']
            self.stats['rtts'].append(rtt)
            
            # Update min/max
            if rtt < self.stats['min_rtt']:
                self.stats['min_rtt'] = rtt
            if rtt > self.stats['max_rtt']:
                self.stats['max_rtt'] = rtt
            
            # Update average
            self.stats['avg_rtt'] = round(sum(self.stats['rtts']) / len(self.stats['rtts']), 2)
        else:
            self.stats['lost'] += 1
        
        self.stats['loss_percent'] = round((self.stats['lost'] / self.stats['sent']) * 100, 2)
    
    def display_result(self, result):
        """Display ping result with colors"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        if result['success']:
            rtt = result['rtt']
            
            # Color based on latency
            if rtt < 50:
                color = Fore.GREEN
                status = "✓"
            elif rtt < 100:
                color = Fore.YELLOW
                status = "⚠"
            else:
                color = Fore.RED
                status = "❗"
            
            # Alert if above threshold
            if rtt > self.alert_threshold:
                print(f"{Fore.RED}🔔 ALERT: High latency {rtt}ms{Style.RESET_ALL}")
            
            print(f"{color}[{timestamp}] {status} {result['host']} - {rtt}ms{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[{timestamp}] ✗ {result['host']} - {result.get('error', 'Timeout')}{Style.RESET_ALL}")
