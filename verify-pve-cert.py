#!/usr/bin/env python3
"""
Check Proxmox VE SSL certificate status
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime


def load_config(config_file):
    """Load configuration from file"""
    config = {}
    with open(config_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line or '=' not in line:
                continue
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    return config


def run_cmd(cmd):
    """Run command and return output"""
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_cert_field(cert_path, field):
    """Get specific field from certificate"""
    return run_cmd(['openssl', 'x509', '-in', cert_path, '-noout', field])


def parse_date(date_str):
    """Parse OpenSSL date to datetime"""
    try:
        return datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z")
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description='Verify Proxmox VE SSL certificate')
    parser.add_argument('--config', '-c', default='/root/deploy-certs/deploy-pve-cert.conf',
                       help='Config file path')
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    config = load_config(args.config)
    cert_path = config.get('PVE_CERT_PATH', '/etc/pve/local/pveproxy-ssl.pem')

    if not os.path.exists(cert_path):
        print(f"Certificate not found: {cert_path}")
        sys.exit(1)

    print("Proxmox VE Certificate Status")
    print("=" * 60)

    # Service status
    result = subprocess.run(['systemctl', 'is-active', 'pveproxy'],
                          capture_output=True, text=True)
    service_status = "Running" if result.returncode == 0 else "Not Running"
    print(f"pveproxy: {service_status}")
    print()

    # Certificate info
    subject = get_cert_field(cert_path, '-subject')
    if subject:
        subject = subject.replace('subject=', '').strip()
        print(f"Subject: {subject}")

    issuer = get_cert_field(cert_path, '-issuer')
    if issuer:
        issuer = issuer.replace('issuer=', '').strip()
        print(f"Issuer: {issuer}")

    # Validity dates
    start_date = get_cert_field(cert_path, '-startdate')
    end_date = get_cert_field(cert_path, '-enddate')

    if start_date:
        print(f"Valid From: {start_date.replace('notBefore=', '')}")

    if end_date:
        end_str = end_date.replace('notAfter=', '')
        print(f"Valid Until: {end_str}")

        # Calculate days remaining
        end_dt = parse_date(end_str)
        if end_dt:
            days = (end_dt - datetime.utcnow()).days
            print(f"\nDays Remaining: {days}")

            if days < 0:
                print("WARNING: Certificate has expired")
            elif days < 30:
                print("WARNING: Certificate expires soon")

    # File info
    print("\n" + "=" * 60)
    stat = os.stat(cert_path)
    mtime = datetime.fromtimestamp(stat.st_mtime)
    print(f"Certificate: {cert_path}")
    print(f"Last Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

    domain = config.get('DOMAIN', 'pve.example.com')
    print(f"\nAccess: https://{domain}:8006")


if __name__ == '__main__':
    main()
