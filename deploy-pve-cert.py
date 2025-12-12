#!/usr/bin/env python3
"""
Deploy SSL certificates from Nginx Proxy Manager to Proxmox VE
"""

import os
import sys
import subprocess
import shutil
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


def run_cmd(cmd, check=True):
    """Run command and return result"""
    result = subprocess.run(cmd, check=check, capture_output=True, text=True)
    return result


def log_message(msg, log_file):
    """Write log message"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a') as f:
        f.write(log_msg + '\n')


def check_ssh_connection(config):
    """Verify SSH connection to Synology"""
    ssh_key = config['SYNOLOGY_SSH_KEY']
    synology_user = config['SYNOLOGY_USER']
    synology_host = config['SYNOLOGY_HOST']

    try:
        run_cmd([
            'ssh', '-i', ssh_key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            f"{synology_user}@{synology_host}", 'echo test'
        ])
        return True
    except subprocess.CalledProcessError:
        return False


def backup_certs(config, log_file):
    """Backup existing certificates"""
    backup_dir = Path(config['BACKUP_DIR'])
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / timestamp
    backup_path.mkdir(parents=True, exist_ok=True)

    cert = Path(config['PVE_CERT_PATH'])
    key = Path(config['PVE_KEY_PATH'])

    if cert.exists() and key.exists():
        # Read and write directly for /etc/pve FUSE filesystem
        with open(cert, 'rb') as src:
            with open(backup_path / 'pveproxy-ssl.pem', 'wb') as dst:
                dst.write(src.read())
        with open(key, 'rb') as src:
            with open(backup_path / 'pveproxy-ssl.key', 'wb') as dst:
                dst.write(src.read())
        log_message(f"Backed up to {backup_path}", log_file)


def download_certs(config, log_file):
    """Download certificates from Synology"""
    ssh_key = config['SYNOLOGY_SSH_KEY']
    synology = f"{config['SYNOLOGY_USER']}@{config['SYNOLOGY_HOST']}"
    npm_path = config['NPM_CERT_PATH']

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Download cert files (use -O for legacy SCP protocol)
        run_cmd(['scp', '-O', '-i', ssh_key, '-o', 'BatchMode=yes',
                f"{synology}:{npm_path}/fullchain.pem", str(tmp_path / 'fullchain.pem')])
        run_cmd(['scp', '-O', '-i', ssh_key, '-o', 'BatchMode=yes',
                f"{synology}:{npm_path}/privkey.pem", str(tmp_path / 'privkey.pem')])

        # Copy to Proxmox paths (read and write directly for /etc/pve FUSE filesystem)
        with open(tmp_path / 'fullchain.pem', 'rb') as src:
            with open(config['PVE_CERT_PATH'], 'wb') as dst:
                dst.write(src.read())
        with open(tmp_path / 'privkey.pem', 'rb') as src:
            with open(config['PVE_KEY_PATH'], 'wb') as dst:
                dst.write(src.read())

    log_message("Certificates downloaded", log_file)


def set_permissions(config, log_file):
    """Set certificate permissions"""
    cert = config['PVE_CERT_PATH']
    key = config['PVE_KEY_PATH']

    run_cmd(['chown', 'root:www-data', cert, key])
    run_cmd(['chmod', '640', cert, key])

    log_message("Permissions set", log_file)


def restart_pveproxy(log_file):
    """Restart pveproxy service"""
    run_cmd(['systemctl', 'restart', 'pveproxy'])
    result = run_cmd(['systemctl', 'is-active', 'pveproxy'], check=False)

    if result.returncode == 0:
        log_message("pveproxy restarted", log_file)
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description='Deploy SSL certs from NPM to Proxmox')
    parser.add_argument('--config', '-c', default='/root/deploy-certs/deploy-pve-cert.conf',
                       help='Config file path')
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    if os.geteuid() != 0:
        print("Error: Must run as root")
        sys.exit(1)

    try:
        config = load_config(args.config)
        log_file = config['LOG_FILE']

        log_message("Starting certificate deployment", log_file)

        # Verify SSH
        if not check_ssh_connection(config):
            log_message("Error: SSH connection failed", log_file)
            sys.exit(1)

        # Backup existing certs
        backup_certs(config, log_file)

        # Download new certs
        download_certs(config, log_file)

        # Set permissions
        set_permissions(config, log_file)

        # Restart service
        if not restart_pveproxy(log_file):
            log_message("Error: pveproxy failed to start", log_file)
            sys.exit(1)

        log_message(f"Deployment complete - https://{config['DOMAIN']}:8006", log_file)

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
