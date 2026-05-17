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

    def single_ping(self, host, count=4):
        """
        Send limited number of pings
        """
        print(f"\n{Fore.GREEN}📡 Sending {count} ping(s) to {host}{Style.RESET_ALL}\n")
        
        for i in range(count):
            result = self.ping_host(host)
            self.results.append(result)
            self.update_statistics(result)
            self.display_result(result)
            time.sleep(1)
        
        self.display_final_report()
    
    def monitor_multiple_hosts(self, hosts_file, interval=5):
        """
        Monitor multiple hosts from a file
        """
        try:
            with open(hosts_file, 'r') as f:
                hosts = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            print(f"\n{Fore.GREEN}🚀 Monitoring {len(hosts)} hosts from {hosts_file}{Style.RESET_ALL}")
            
            while True:
                for host in hosts:
                    result = self.ping_host(host)
                    self.results.append(result)
                    self.update_statistics(result)
                    self.display_result(result)
                
                print(f"{Fore.CYAN}{'-'*60}{Style.RESET_ALL}")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.display_final_report()
            self.save_log()
        except FileNotFoundError:
            print(f"{Fore.RED}✗ File {hosts_file} not found!{Style.RESET_ALL}")
    
    def display_final_report(self):
        """Display final report after monitoring"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.GREEN}📋 FINAL MONITORING REPORT")
        print(f"{Fore.CYAN}{'='*60}")
        
        self.display_statistics()
        
        # Uptime calculation
        if self.stats['sent'] > 0:
            uptime = (self.stats['received'] / self.stats['sent']) * 100
            print(f"{Fore.WHITE}📈 Uptime: {uptime:.2f}%")
        
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    def set_alert_threshold(self, threshold):
        """Set custom alert threshold"""
        self.alert_threshold = threshold
        print(f"{Fore.GREEN}✓ Alert threshold set to {threshold}ms{Style.RESET_ALL}")
    
    def export_csv(self, filename="ping_report.csv"):

def main():
    """Main CLI interface"""
    monitor = PingMonitor()
    monitor.print_banner()
    
    while True:
        print(f"\n{Fore.CYAN}📌 MAIN MENU")
        print(f"{Fore.WHITE}1. Continuous Ping Monitor (Real-time)")
        print(f"2. Single Ping Test (4 pings)")
        print(f"3. Custom Ping Count")
        print(f"4. Monitor Multiple Hosts (from file)")
        print(f"5. Set Alert Threshold")
        print(f"6. Export Report to CSV")
        print(f"7. View Last Results")
        print(f"0. Exit")
        
        choice = input(f"\n{Fore.GREEN}➜ Select option: {Style.RESET_ALL}").strip()
        
        if choice == '1':
            host = input("Enter host/IP to monitor (e.g., google.com or 8.8.8.8): ").strip()
            interval = input("Interval between pings (seconds) [default=1]: ").strip()
            interval = int(interval) if interval else 1
            monitor.continuous_monitor(host, interval)
            
        elif choice == '2':
            host = input("Enter host/IP: ").strip()
            monitor.single_ping(host, 4)
            
        elif choice == '3':
            host = input("Enter host/IP: ").strip()
            count = int(input("Number of pings: ").strip())
            monitor.single_ping(host, count)
            
        elif choice == '4':
            filepath = input("Enter hosts file path (e.g., targets.txt): ").strip()
            interval = input("Interval between rounds (seconds) [default=5]: ").strip()
            interval = int(interval) if interval else 5
            monitor.monitor_multiple_hosts(filepath, interval)
            
        elif choice == '5':
            threshold = int(input("Enter alert threshold in ms (e.g., 100): ").strip())
            monitor.set_alert_threshold(threshold)
            
        elif choice == '6':
            filename = input("Enter CSV filename [default=ping_report.csv]: ").strip()
            filename = filename if filename else "ping_report.csv"
            monitor.export_csv(filename)
            
        elif choice == '7':
            if monitor.results:
                print(f"\n{Fore.CYAN}Last 10 results:{Style.RESET_ALL}")
                for result in monitor.results[-10:]:
                    if result['success']:
                        print(f"  ✓ {result['host']} - {result['rtt']}ms")
                    else:
                        print(f"  ✗ {result['host']} - Failed")
            else:
                print(f"{Fore.YELLOW}No results yet{Style.RESET_ALL}")
                
        elif choice == '0':
            print(f"{Fore.GREEN}👋 Goodbye!{Style.RESET_ALL}")
            break
        
        else:
            print(f"{Fore.RED}Invalid option!{Style.RESET_ALL}")
        
        input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
