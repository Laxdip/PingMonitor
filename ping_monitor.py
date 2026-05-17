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

    def display_statistics(self):
        """Display comprehensive statistics"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.YELLOW}📊 STATISTICS SUMMARY")
        print(f"{Fore.CYAN}{'='*60}")
        
        print(f"{Fore.WHITE}📦 Packets: Sent={self.stats['sent']} | Received={self.stats['received']} | Lost={self.stats['lost']}")
        print(f"{Fore.WHITE}📉 Loss: {self.stats.get('loss_percent', 0)}%")
        
        if self.stats['received'] > 0:
            print(f"{Fore.GREEN}⏱️  Latency: Min={self.stats['min_rtt']}ms | Max={self.stats['max_rtt']}ms | Avg={self.stats['avg_rtt']}ms")
        
        # Quality rating
        loss = self.stats.get('loss_percent', 100)
        if loss == 0 and self.stats['avg_rtt'] < 50:
            quality = f"{Fore.GREEN}EXCELLENT"
        elif loss < 5 and self.stats['avg_rtt'] < 100:
            quality = f"{Fore.YELLOW}GOOD"
        elif loss < 20:
            quality = f"{Fore.MAGENTA}POOR"
        else:
            quality = f"{Fore.RED}CRITICAL"
        
        print(f"{Fore.WHITE}🎯 Connection Quality: {quality}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    def save_log(self):
        """Save results to JSON log file"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'stats': self.stats,
            'recent_results': self.results[-100:]  # Last 100 results
        }
        
        try:
            # Load existing logs
            existing_logs = []
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    existing_logs = json.load(f)
            
            # Add new entry
            existing_logs.append(log_entry)
            
            # Keep last 1000 entries
            if len(existing_logs) > 1000:
                existing_logs = existing_logs[-1000:]
            
            # Save to file
            with open(self.log_file, 'w') as f:
                json.dump(existing_logs, f, indent=2)
            
            print(f"{Fore.GREEN}✓ Log saved to {self.log_file}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Failed to save log: {e}{Style.RESET_ALL}")
    
    def continuous_monitor(self, host, interval=1):
        """
        Continuously monitor a host
        """
        self.is_monitoring = True
        self.stats = {
            'sent': 0, 'received': 0, 'lost': 0,
            'min_rtt': float('inf'), 'max_rtt': 0,
            'avg_rtt': 0, 'rtts': []
        }
        self.results = []
        
        print(f"\n{Fore.GREEN}🚀 Starting continuous monitoring of {host}")
        print(f"{Fore.YELLOW}📡 Interval: {interval}s | Alert threshold: {self.alert_threshold}ms")
        print(f"{Fore.CYAN}Press Ctrl+C to stop{Style.RESET_ALL}\n")
        
        try:
            while self.is_monitoring:
                result = self.ping_host(host)
                self.results.append(result)
                self.update_statistics(result)
                self.display_result(result)
                
                # Show stats every 10 pings
                if self.stats['sent'] % 10 == 0:
                    self.display_statistics()
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}🛑 Monitoring stopped by user{Style.RESET_ALL}")
            self.is_monitoring = False
            self.display_final_report()
            self.save_log()
    
