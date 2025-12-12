# Proxmox VE Certificate Deployment from NPM

Deploy Let's Encrypt SSL certificates from Nginx Proxy Manager to Proxmox VE.

## The Problem

Proxmox VE ships with self-signed certificates, which trigger browser warnings. If you're already using Nginx Proxy Manager to manage Let's Encrypt certificates for other services, you probably want to use proper certificates for Proxmox too.

The catch is that Proxmox runs its own HTTPS server (not just HTTP like most Docker containers), so you can't simply proxy through NPM. You need to deploy the actual certificate files to Proxmox.

This script automates that process - it pulls certificates from your NPM instance (running on Synology or elsewhere) and deploys them to Proxmox VE.

## How It Works

1. NPM obtains and renews Let's Encrypt certificates via DNS-01 challenge
2. Certificates are stored in NPM's Docker volume
3. This script (running on Proxmox) pulls the certs via SSH/SCP
4. Deploys them to `/etc/pve/local/` with correct permissions
5. Restarts the `pveproxy` service

## Requirements

- Proxmox VE 7.0+
- Nginx Proxy Manager managing a certificate for your Proxmox domain
- SSH access from Proxmox to the host running NPM
- Python 3 on Proxmox (usually pre-installed)

## Setup

### 1. Configure NPM

Create a certificate in Nginx Proxy Manager:
- Domain: Your Proxmox domain (e.g., `pve.example.com`)
- Use DNS Challenge (if using internal/local access)
- Or HTTP Challenge (if publicly accessible)

Note the certificate ID from NPM (you'll see it in the file path, e.g., `npm-35`).

### 2. Find Certificate Path

SSH to your NPM host and locate the certificate:

```bash
find /volume1/docker/nginx-proxy-manager -name "fullchain.pem" | grep live
```

You should see something like:
```
/volume1/docker/nginx-proxy-manager/letsencrypt/live/npm-35/fullchain.pem
```

### 3. Configure Deploy Script

Copy the example config and edit with your settings:

```bash
cp deploy-pve-cert.conf.example deploy-pve-cert.conf
nano deploy-pve-cert.conf
```

Update these values:
- `SYNOLOGY_HOST` - Your NPM host IP
- `SYNOLOGY_USER` - SSH username
- `NPM_CERT_PATH` - Path to certificate (e.g., `/volume1/docker/nginx-proxy-manager/letsencrypt/live/npm-35`)
- `DOMAIN` - Your Proxmox domain

### 4. Copy Files to Proxmox

```bash
ssh root@your-proxmox "mkdir -p /root/deploy-certs"
scp deploy-pve-cert.conf root@your-proxmox:/root/deploy-certs/
scp deploy-pve-cert.py root@your-proxmox:/root/deploy-certs/
scp verify-pve-cert.py root@your-proxmox:/root/deploy-certs/
```

### 5. Setup SSH Keys

On Proxmox:

```bash
# Make scripts executable
chmod +x /root/deploy-certs/deploy-pve-cert.py /root/deploy-certs/verify-pve-cert.py

# Generate SSH key
ssh-keygen -t ed25519 -f /root/.ssh/synology_npm -N ""

# Copy to NPM host
ssh-copy-id -i /root/.ssh/synology_npm.pub user@npm-host

# Test connection
ssh -i /root/.ssh/synology_npm user@npm-host hostname
```

### 6. Deploy Certificate

```bash
python3 /root/deploy-certs/deploy-pve-cert.py
```

The script will:
- Verify SSH connection
- Backup existing certificates
- Download new certificates from NPM
- Set correct permissions
- Restart pveproxy

### 7. Verify

```bash
python3 /root/deploy-certs/verify-pve-cert.py
```

Access Proxmox at `https://your-domain:8006` - you should see a valid certificate.

## Usage

When NPM renews the certificate (every 60-90 days), run the deployment script again:

```bash
python3 /root/deploy-certs/deploy-pve-cert.py
```

You can automate this with cron if desired:

```bash
crontab -e
# Add: 0 3 * * * /usr/bin/python3 /root/deploy-certs/deploy-pve-cert.py >> /var/log/pve-cert-deploy.log 2>&1
```

## Troubleshooting

**SSH connection fails:**
```bash
ssh -i /root/.ssh/synology_npm user@npm-host
```
If prompted for password, re-run `ssh-copy-id`.

**Certificate path not found:**

Find the correct path on NPM host:
```bash
find /volume*/docker/nginx-proxy-manager -name "fullchain.pem"
```

**pveproxy won't start:**

Check permissions:
```bash
ls -la /etc/pve/local/pveproxy-ssl.*
# Should be: -rw-r----- 1 root www-data
```

**Certificate still shows as invalid:**

Clear browser cache or check deployment logs:
```bash
tail -f /var/log/pve-cert-deploy.log
```

## Files

- `deploy-pve-cert.conf` - Configuration file
- `deploy-pve-cert.py` - Main deployment script
- `verify-pve-cert.py` - Certificate verification tool

## Notes

- Certificates are backed up to `/root/pve-cert-backups/` before each deployment
- Logs are written to `/var/log/pve-cert-deploy.log`
- The script is idempotent - safe to run multiple times
- Works with wildcard certificates if your domain matches
