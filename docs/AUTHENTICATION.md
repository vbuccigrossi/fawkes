# Fawkes Authentication Guide

This guide covers the authentication and encryption features in Fawkes for securing distributed fuzzing deployments.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Security Features](#security-features)
- [Setup Instructions](#setup-instructions)
- [Configuration Reference](#configuration-reference)
- [CLI Tool Reference](#cli-tool-reference)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)
- [Migration Guide](#migration-guide)

## Overview

Fawkes supports optional authentication and TLS encryption for all distributed modes:
- **Basic Controller/Worker Mode**: Simple job distribution
- **Scheduled Controller/Worker Mode**: Advanced scheduler with load balancing

When enabled, authentication and encryption protect:
- Controller API endpoints from unauthorized access
- Worker nodes from accepting malicious jobs
- Network traffic from eavesdropping and tampering
- System from credential theft and replay attacks

### Authentication Methods

1. **API Keys**: For controller authentication (recommended for automation)
2. **User Accounts**: For administrative access and future web interfaces
3. **Session Tokens**: For temporary authenticated sessions

### Encryption

- **TLS 1.2+**: All network communication encrypted
- **Strong Ciphers**: ECDHE+AESGCM, ECDHE+CHACHA20, DHE+AESGCM
- **Self-Signed Certificates**: Auto-generated if not provided
- **Custom Certificates**: Support for production CA-signed certificates

## Quick Start

### 1. Initialize Authentication System

```bash
# Initialize with default admin user
./fawkes-auth init

# Enter admin password when prompted
# This creates ~/.fawkes/auth.db
```

### 2. Create API Key for Controller

```bash
# Generate API key for controller authentication
./fawkes-auth key create controller-01

# Output:
# API Key created successfully!
# Key ID: 1
# Key Name: controller-01
# API Key: <random-key-string>
# IMPORTANT: Save this key - it will not be shown again!
```

### 3. Generate TLS Certificates

```bash
# Auto-generate self-signed certificates
./fawkes-auth cert generate

# Certificates saved to:
# ~/.fawkes/certs/fawkes.crt
# ~/.fawkes/certs/fawkes.key
```

### 4. Configure Controller

Create `controller-config.yaml`:

```yaml
auth_enabled: true
tls_enabled: true
controller_api_key: "<paste-api-key-here>"
controller_db_path: ~/.fawkes/controller.db

workers:
  - 192.168.1.10
  - 192.168.1.11

job_dir: ~/.fawkes/jobs/
poll_interval: 60
log_level: INFO
```

### 5. Configure Worker

Create `worker-config.yaml` and copy to each worker node:

```yaml
auth_enabled: true
tls_enabled: true
auth_db_path: ~/.fawkes/auth.db

controller_host: 0.0.0.0
controller_port: 9999
log_level: INFO
```

### 6. Deploy Authentication Database

Copy the authentication database to each worker node:

```bash
# On controller
scp ~/.fawkes/auth.db worker-01:~/.fawkes/
scp ~/.fawkes/auth.db worker-02:~/.fawkes/
```

### 7. Start Services

```bash
# On each worker
./fawkes-worker --config worker-config.yaml

# On controller
./fawkes-controller --config controller-config.yaml
```

## Security Features

### Password Security

- **Algorithm**: PBKDF2-HMAC-SHA256
- **Iterations**: 100,000 (OWASP recommended minimum)
- **Salt**: 32-byte random salt per password
- **Storage**: Only hashed passwords stored, never plaintext

### API Key Security

- **Generation**: Cryptographically secure random tokens (32 bytes)
- **Hashing**: SHA-256 hashed before storage
- **Display**: Shown only once during creation
- **Revocation**: Can be revoked instantly via CLI

### Account Protection

- **Failed Login Tracking**: Counts consecutive failures
- **Account Lockout**: 5 failed attempts triggers lockout
- **Lockout Duration**: 15 minutes (configurable in auth_db.py)
- **Automatic Unlock**: Accounts unlock after timeout

### Session Management

- **Token Security**: Cryptographically secure random tokens
- **Expiration**: 24-hour default session lifetime
- **IP Tracking**: Session tied to IP address
- **User Agent**: Browser fingerprinting stored
- **Revocation**: Sessions can be terminated manually

### Audit Logging

All security events are logged:
- User login attempts (success and failure)
- API key usage
- Session creation and expiration
- Permission checks
- Administrative actions
- Resource access

### Role-Based Access Control

Four built-in roles with granular permissions:

**Admin** (29 permissions): Full system access
- User management, role assignment, API key management
- Job creation, monitoring, cancellation
- Worker management, system configuration
- Audit log access

**Operator** (15 permissions): Job and worker management
- Job creation, monitoring, cancellation
- Worker monitoring and management
- Read-only access to system info
- No user/role management

**Viewer** (6 permissions): Read-only access
- View jobs, workers, crashes, system status
- No modification permissions

**Worker** (4 permissions): Worker node operations
- Register with controller
- Send heartbeats and status updates
- Receive and report jobs
- No administrative access

## Setup Instructions

### Initial System Setup

1. **Create Fawkes Directory Structure**

```bash
mkdir -p ~/.fawkes/certs
mkdir -p ~/.fawkes/jobs
chmod 700 ~/.fawkes  # Protect directory
```

2. **Initialize Authentication Database**

```bash
./fawkes-auth init

# Enter admin credentials:
# Username: admin
# Password: <secure-password>
# Email: admin@example.com
# Full Name: Administrator
```

3. **Generate TLS Certificates**

For development/testing:
```bash
./fawkes-auth cert generate
```

For production with custom certificates:
```bash
# Copy your CA-signed certificates
cp /path/to/your/cert.crt ~/.fawkes/certs/fawkes.crt
cp /path/to/your/key.key ~/.fawkes/certs/fawkes.key
chmod 600 ~/.fawkes/certs/fawkes.key  # Protect private key
```

### User Management

**Create a New User**

```bash
./fawkes-auth user add operator1 \
  --email operator1@example.com \
  --full-name "Operator One" \
  --role operator

# Enter password when prompted
```

**List All Users**

```bash
./fawkes-auth user list

# Output:
# ID  Username    Email                   Role      Enabled
# 1   admin       admin@example.com       admin     Yes
# 2   operator1   operator1@example.com   operator  Yes
```

**Change User Password**

```bash
./fawkes-auth user passwd operator1

# Enter new password when prompted
```

**Disable User Account**

```bash
./fawkes-auth user disable operator1
```

**Enable User Account**

```bash
./fawkes-auth user enable operator1
```

**Delete User**

```bash
./fawkes-auth user delete operator1
```

### API Key Management

**Create API Key for Controller**

```bash
./fawkes-auth key create controller-01 \
  --type controller \
  --permissions job:create,job:read,job:cancel,worker:read

# IMPORTANT: Copy the API key immediately - it won't be shown again!
```

**Create API Key for Worker**

```bash
./fawkes-auth key create worker-01 \
  --type worker \
  --permissions worker:register,worker:heartbeat,job:receive,job:report
```

**List API Keys**

```bash
./fawkes-auth key list

# Output:
# ID  Name           Type        Created              Enabled
# 1   controller-01  controller  2025-11-14 10:30:00  Yes
# 2   worker-01      worker      2025-11-14 10:31:00  Yes
```

**Revoke API Key**

```bash
./fawkes-auth key revoke 2
```

**Delete API Key**

```bash
./fawkes-auth key delete 2
```

### Distributed Deployment

**Option 1: Shared Authentication Database**

If workers have access to shared filesystem (NFS, etc.):

```yaml
# worker-config.yaml on all workers
auth_enabled: true
auth_db_path: /shared/fawkes/auth.db
```

**Option 2: Copy Authentication Database**

If workers are isolated:

```bash
# On controller after creating users/keys
scp ~/.fawkes/auth.db worker-01:~/.fawkes/
scp ~/.fawkes/auth.db worker-02:~/.fawkes/

# Update database on workers when users/keys change
```

**Option 3: Database Replication**

For large deployments, use database replication:

```bash
# Set up periodic sync (cron job on workers)
*/5 * * * * rsync -av controller:~/.fawkes/auth.db ~/.fawkes/auth.db
```

### TLS Certificate Deployment

**Self-Signed Certificates (Development)**

```bash
# Generate on controller
./fawkes-auth cert generate

# Copy to all workers
scp ~/.fawkes/certs/fawkes.crt worker-01:~/.fawkes/certs/
scp ~/.fawkes/certs/fawkes.key worker-01:~/.fawkes/certs/
```

**CA-Signed Certificates (Production)**

```bash
# Generate CSR
openssl req -new -newkey rsa:2048 -nodes \
  -keyout ~/.fawkes/certs/fawkes.key \
  -out ~/.fawkes/certs/fawkes.csr

# Submit CSR to your CA, receive signed certificate
# Copy certificate and key to all nodes
```

## Configuration Reference

### Controller Configuration

**Basic Controller** (`controller.yaml`):

```yaml
# Authentication and Encryption
auth_enabled: true              # Enable authentication
tls_enabled: true               # Enable TLS encryption
controller_api_key: "<api-key>" # API key for authentication

# TLS Certificate paths (optional, auto-generated if not specified)
tls_cert: ~/.fawkes/certs/fawkes.crt
tls_key: ~/.fawkes/certs/fawkes.key

# Database path
controller_db_path: ~/.fawkes/controller.db

# Worker nodes
workers:
  - 192.168.1.10
  - 192.168.1.11

# Job directory
job_dir: ~/.fawkes/jobs/

# Polling interval (seconds)
poll_interval: 60

# Logging
log_level: INFO
```

**Scheduled Controller** (`scheduled-controller.yaml`):

```yaml
# Authentication and Encryption
auth_enabled: true
tls_enabled: true
controller_api_key: "<api-key>"

# TLS Certificate paths
# tls_cert: ~/.fawkes/certs/fawkes.crt
# tls_key: ~/.fawkes/certs/fawkes.key

# Scheduler database
controller_db_path: ~/.fawkes/scheduler.db

# Scheduler configuration
allocation_strategy: load_aware  # Options: load_aware, round_robin, first_fit
heartbeat_timeout: 90            # Seconds before marking worker offline

# Worker nodes with capabilities
workers:
  - ip: 192.168.1.10
    hostname: worker-01
    tags:
      - gpu
      - high-cpu
  - ip: 192.168.1.11
    hostname: worker-02
    tags:
      - high-memory

# Polling interval
poll_interval: 30

# Logging
log_level: INFO
```

### Worker Configuration

**Basic Worker** (`worker.yaml`):

```yaml
# Authentication and Encryption
auth_enabled: true
tls_enabled: true

# Authentication database path
auth_db_path: ~/.fawkes/auth.db

# TLS Certificate paths (must match controller certificates)
# tls_cert: ~/.fawkes/certs/fawkes.crt
# tls_key: ~/.fawkes/certs/fawkes.key

# Network configuration
controller_host: 0.0.0.0  # Listen on all interfaces
controller_port: 9999

# Logging
log_level: INFO
```

**Scheduled Worker** (`scheduled-worker.yaml`):

```yaml
# Authentication and Encryption
auth_enabled: true
tls_enabled: true

# Authentication database path
auth_db_path: ~/.fawkes/auth.db

# TLS Certificate paths
# tls_cert: ~/.fawkes/certs/fawkes.crt
# tls_key: ~/.fawkes/certs/fawkes.key

# Network configuration
controller_host: 0.0.0.0
controller_port: 9999

# Worker tags for scheduler (optional)
worker_tags:
  - production
  - x86_64

# Logging
log_level: INFO
```

### Configuration Options

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `auth_enabled` | bool | No | false | Enable authentication |
| `tls_enabled` | bool | No | false | Enable TLS encryption |
| `controller_api_key` | string | Yes* | - | API key for controller (*if auth_enabled) |
| `auth_db_path` | string | Yes* | ~/.fawkes/auth.db | Path to auth database (*if auth_enabled) |
| `tls_cert` | string | No | ~/.fawkes/certs/fawkes.crt | TLS certificate path |
| `tls_key` | string | No | ~/.fawkes/certs/fawkes.key | TLS private key path |
| `controller_db_path` | string | Yes | - | Controller database path |
| `allocation_strategy` | string | No | load_aware | Scheduler strategy (scheduled mode) |
| `heartbeat_timeout` | int | No | 90 | Worker timeout in seconds |
| `worker_tags` | list | No | [] | Worker capability tags |
| `workers` | list | Yes | - | Worker IP addresses or configs |
| `job_dir` | string | Yes | - | Job directory (controller only) |
| `poll_interval` | int | No | 60 | Polling interval in seconds |
| `log_level` | string | No | INFO | Logging level |

## CLI Tool Reference

### fawkes-auth Command

```bash
./fawkes-auth <command> [options]
```

### Commands

#### init - Initialize Authentication System

```bash
./fawkes-auth init [--db-path PATH]

Options:
  --db-path PATH    Path to authentication database (default: ~/.fawkes/auth.db)

Interactive prompts:
  - Admin username
  - Admin password
  - Admin email
  - Admin full name
```

#### user - User Management

**Add User**
```bash
./fawkes-auth user add <username> [options]

Options:
  --email EMAIL           User email address
  --full-name NAME        User full name
  --role ROLE             User role (admin, operator, viewer, worker)
  --db-path PATH          Database path

Example:
  ./fawkes-auth user add operator1 \
    --email operator1@example.com \
    --full-name "Operator One" \
    --role operator
```

**List Users**
```bash
./fawkes-auth user list [--db-path PATH]
```

**Change Password**
```bash
./fawkes-auth user passwd <username> [--db-path PATH]
```

**Disable User**
```bash
./fawkes-auth user disable <username> [--db-path PATH]
```

**Enable User**
```bash
./fawkes-auth user enable <username> [--db-path PATH]
```

**Delete User**
```bash
./fawkes-auth user delete <username> [--db-path PATH]
```

#### key - API Key Management

**Create Key**
```bash
./fawkes-auth key create <key-name> [options]

Options:
  --type TYPE             Key type (controller, worker, custom)
  --permissions PERMS     Comma-separated permissions
  --created-by USER       Creator username
  --worker-id ID          Worker ID (for worker keys)
  --db-path PATH          Database path

Examples:
  # Controller key with specific permissions
  ./fawkes-auth key create controller-01 \
    --type controller \
    --permissions job:create,job:read,worker:read

  # Worker key with default worker permissions
  ./fawkes-auth key create worker-01 \
    --type worker \
    --worker-id worker-01
```

**List Keys**
```bash
./fawkes-auth key list [--db-path PATH]
```

**Revoke Key**
```bash
./fawkes-auth key revoke <key-id> [--db-path PATH]
```

**Enable Key**
```bash
./fawkes-auth key enable <key-id> [--db-path PATH]
```

**Delete Key**
```bash
./fawkes-auth key delete <key-id> [--db-path PATH]
```

#### cert - TLS Certificate Management

**Generate Certificates**
```bash
./fawkes-auth cert generate [options]

Options:
  --cert-file PATH        Certificate output path (default: ~/.fawkes/certs/fawkes.crt)
  --key-file PATH         Key output path (default: ~/.fawkes/certs/fawkes.key)
  --days DAYS             Validity period in days (default: 365)

Example:
  ./fawkes-auth cert generate --days 730
```

**Verify Certificate**
```bash
./fawkes-auth cert verify [options]

Options:
  --cert-file PATH        Certificate path (default: ~/.fawkes/certs/fawkes.crt)

Output:
  - Subject information
  - Validity period
  - Expiration warning if < 30 days
```

#### audit - View Audit Logs

```bash
./fawkes-auth audit [options]

Options:
  --limit N               Show last N entries (default: 50)
  --user USERNAME         Filter by username
  --action ACTION         Filter by action
  --success BOOL          Filter by success (true/false)
  --db-path PATH          Database path

Examples:
  # Show last 100 audit entries
  ./fawkes-auth audit --limit 100

  # Show failed login attempts
  ./fawkes-auth audit --action user:login --success false

  # Show all actions by specific user
  ./fawkes-auth audit --user operator1
```

## Security Best Practices

### Strong Passwords

- **Minimum Length**: 12 characters
- **Complexity**: Mix uppercase, lowercase, numbers, symbols
- **Uniqueness**: Don't reuse passwords from other systems
- **Storage**: Use password manager for admin passwords
- **Rotation**: Change passwords periodically (90 days recommended)

### API Key Management

- **One Key Per Controller**: Create separate keys for each controller instance
- **Descriptive Names**: Use names like "controller-prod-01" for easy identification
- **Secure Storage**: Store keys in configuration files with restricted permissions
- **Immediate Revocation**: Revoke compromised keys immediately
- **Regular Rotation**: Rotate keys every 90-180 days
- **Monitor Usage**: Review audit logs for unusual API key activity

### File Permissions

```bash
# Protect authentication database
chmod 600 ~/.fawkes/auth.db

# Protect private key
chmod 600 ~/.fawkes/certs/fawkes.key

# Protect configuration files with API keys
chmod 600 controller-config.yaml

# Protect Fawkes directory
chmod 700 ~/.fawkes
```

### Network Security

- **Firewall Rules**: Only allow controller-to-worker traffic on port 9999
- **Network Segmentation**: Isolate fuzzing infrastructure from production networks
- **VPN/Tunnel**: Use VPN or SSH tunnels for cross-datacenter communication
- **Certificate Validation**: Use CA-signed certificates in production

### Database Security

- **Backup Regularly**: Backup auth.db and controller databases
- **Encrypted Backups**: Encrypt database backups
- **Access Control**: Restrict filesystem access to Fawkes user only
- **Audit Review**: Regularly review audit logs for suspicious activity

### Deployment Security

**Development/Testing**:
- Self-signed certificates acceptable
- Can disable TLS on localhost
- Simpler password requirements

**Production**:
- **MUST** use TLS with CA-signed certificates
- **MUST** use strong passwords (12+ chars)
- **MUST** enable authentication
- **MUST** review audit logs regularly
- **MUST** implement firewall rules
- **SHOULD** use network segmentation
- **SHOULD** rotate credentials regularly

### Incident Response

If credentials are compromised:

1. **Revoke Immediately**
```bash
# Revoke compromised API key
./fawkes-auth key revoke <key-id>

# Disable compromised user
./fawkes-auth user disable <username>
```

2. **Review Audit Logs**
```bash
# Check for unauthorized activity
./fawkes-auth audit --user <compromised-user>
./fawkes-auth audit --action job:create --success true
```

3. **Rotate Credentials**
```bash
# Create new API key
./fawkes-auth key create controller-new

# Update controller configuration
# Deploy new configuration

# Delete old key after verification
./fawkes-auth key delete <old-key-id>
```

4. **Investigate Impact**
- Check job history for unauthorized jobs
- Review worker activity during compromise window
- Examine crash reports for suspicious testcases

## Troubleshooting

### Authentication Errors

**Error: "Authentication failed: Invalid API key"**

Causes:
- API key not copied correctly from creation output
- API key revoked or deleted
- API key not enabled

Solutions:
```bash
# List API keys to verify status
./fawkes-auth key list

# Create new API key if needed
./fawkes-auth key create controller-new

# Update controller configuration with new key
```

**Error: "Authentication failed: User account is locked"**

Causes:
- Too many failed login attempts (5+)
- Account locked by administrator

Solutions:
```bash
# Wait 15 minutes for automatic unlock, or
# Manually unlock account (admin only)
./fawkes-auth user enable <username>
```

**Error: "Authentication database not found"**

Causes:
- auth_db_path points to non-existent file
- Database not copied to worker node

Solutions:
```bash
# Initialize database on controller
./fawkes-auth init

# Copy to worker
scp ~/.fawkes/auth.db worker-01:~/.fawkes/

# Verify path in configuration
cat worker-config.yaml | grep auth_db_path
```

### TLS Errors

**Error: "SSL handshake failed"**

Causes:
- Certificate/key mismatch
- Certificate expired
- Certificate not present on worker

Solutions:
```bash
# Verify certificate validity
./fawkes-auth cert verify

# Regenerate if expired
./fawkes-auth cert generate

# Ensure certificates match on all nodes
md5sum ~/.fawkes/certs/fawkes.crt
```

**Error: "Certificate verify failed"**

Causes:
- Self-signed certificate not trusted
- Certificate hostname mismatch
- Certificate chain incomplete

Solutions:
```bash
# For self-signed certificates, this is expected
# Fawkes handles self-signed certs automatically

# For CA-signed certs, verify chain:
openssl verify -CAfile ca-bundle.crt ~/.fawkes/certs/fawkes.crt
```

### Connection Errors

**Error: "Connection refused"**

Causes:
- Worker not running
- Firewall blocking port 9999
- Wrong IP address in controller config

Solutions:
```bash
# Verify worker is running
ps aux | grep fawkes-worker

# Test network connectivity
telnet worker-01 9999

# Check firewall
sudo iptables -L | grep 9999
```

**Error: "Connection timeout"**

Causes:
- Network routing issues
- Worker behind NAT
- Slow network causing TLS timeout

Solutions:
```bash
# Test basic network connectivity
ping worker-01

# Test port connectivity
nc -zv worker-01 9999

# Check for NAT/firewall issues
traceroute worker-01
```

### Permission Errors

**Error: "Permission denied: job:create"**

Causes:
- API key lacks required permission
- User role doesn't include permission

Solutions:
```bash
# Check API key permissions
./fawkes-auth key list

# Create new key with required permissions
./fawkes-auth key create controller-01 \
  --permissions job:create,job:read,job:cancel,worker:read
```

**Error: "Worker registration failed"**

Causes:
- Worker API key lacks worker:register permission
- Controller not configured to accept workers

Solutions:
```bash
# Create worker API key with correct permissions
./fawkes-auth key create worker-01 \
  --type worker \
  --permissions worker:register,worker:heartbeat,job:receive,job:report
```

### Database Errors

**Error: "Database is locked"**

Causes:
- Multiple processes accessing SQLite database
- Stale lock from crashed process

Solutions:
```bash
# Check for multiple processes
ps aux | grep fawkes

# Remove stale lock (if no processes running)
rm ~/.fawkes/auth.db-journal
```

**Error: "Database schema version mismatch"**

Causes:
- Outdated database from previous Fawkes version
- Database corrupted

Solutions:
```bash
# Backup existing database
cp ~/.fawkes/auth.db ~/.fawkes/auth.db.backup

# Reinitialize (WARNING: deletes all users/keys)
./fawkes-auth init

# Recreate users and API keys
```

### Debugging Tips

**Enable Debug Logging**

```yaml
# In configuration file
log_level: DEBUG
```

**Check Audit Logs**

```bash
# View recent authentication activity
./fawkes-auth audit --limit 100

# View failed authentications
./fawkes-auth audit --success false
```

**Test Authentication Manually**

```python
# Python test script
from fawkes.db.auth_db import AuthDB

db = AuthDB("~/.fawkes/auth.db")

# Test API key validation
principal = db.validate_api_key("your-api-key-here")
print(f"Validated: {principal}")

# Test user authentication
success = db.authenticate_user("username", "password")
print(f"Login: {success}")
```

**Verify TLS Configuration**

```bash
# Test TLS connection
openssl s_client -connect worker-01:9999 \
  -cert ~/.fawkes/certs/fawkes.crt \
  -key ~/.fawkes/certs/fawkes.key
```

## Migration Guide

### Migrating from Unauthenticated to Authenticated Setup

This guide helps you add authentication to existing Fawkes deployments.

#### Step 1: Backup Everything

```bash
# Backup controller database
cp ~/.fawkes/controller.db ~/.fawkes/controller.db.backup

# Backup scheduler database (if using scheduled mode)
cp ~/.fawkes/scheduler.db ~/.fawkes/scheduler.db.backup

# Backup configuration files
cp controller-config.yaml controller-config.yaml.backup
cp worker-config.yaml worker-config.yaml.backup
```

#### Step 2: Stop All Services

```bash
# Stop all workers
pkill -f fawkes-worker

# Stop controller
pkill -f fawkes-controller
```

#### Step 3: Initialize Authentication

```bash
# Initialize authentication system
./fawkes-auth init

# Create API key for controller
./fawkes-auth key create controller-prod \
  --type controller \
  --permissions job:create,job:read,job:cancel,worker:read

# IMPORTANT: Copy the API key output
```

#### Step 4: Generate TLS Certificates

```bash
# Generate self-signed certificates
./fawkes-auth cert generate

# Or copy production certificates
cp /path/to/prod/cert.crt ~/.fawkes/certs/fawkes.crt
cp /path/to/prod/key.key ~/.fawkes/certs/fawkes.key
chmod 600 ~/.fawkes/certs/fawkes.key
```

#### Step 5: Update Controller Configuration

```yaml
# Add to controller-config.yaml

# Authentication and Encryption
auth_enabled: true
tls_enabled: true
controller_api_key: "<paste-api-key-here>"

# TLS paths (optional - auto-generated)
# tls_cert: ~/.fawkes/certs/fawkes.crt
# tls_key: ~/.fawkes/certs/fawkes.key

# Keep existing configuration
controller_db_path: ~/.fawkes/controller.db
workers:
  - 192.168.1.10
  - 192.168.1.11
job_dir: ~/.fawkes/jobs/
poll_interval: 60
log_level: INFO
```

#### Step 6: Update Worker Configuration

```yaml
# Add to worker-config.yaml

# Authentication and Encryption
auth_enabled: true
tls_enabled: true
auth_db_path: ~/.fawkes/auth.db

# TLS paths (optional - auto-generated)
# tls_cert: ~/.fawkes/certs/fawkes.crt
# tls_key: ~/.fawkes/certs/fawkes.key

# Keep existing configuration
controller_host: 0.0.0.0
controller_port: 9999
log_level: INFO
```

#### Step 7: Deploy to Workers

```bash
# Copy auth database to all workers
for worker in worker-01 worker-02 worker-03; do
  scp ~/.fawkes/auth.db ${worker}:~/.fawkes/
  scp ~/.fawkes/certs/fawkes.crt ${worker}:~/.fawkes/certs/
  scp ~/.fawkes/certs/fawkes.key ${worker}:~/.fawkes/certs/
  scp worker-config.yaml ${worker}:~/
done
```

#### Step 8: Restart Services

```bash
# Start workers with new configuration
ssh worker-01 './fawkes-worker --config worker-config.yaml &'
ssh worker-02 './fawkes-worker --config worker-config.yaml &'

# Start controller with new configuration
./fawkes-controller --config controller-config.yaml
```

#### Step 9: Verify

```bash
# Check controller logs for successful authentication
tail -f ~/.fawkes/controller.log | grep -i auth

# Check audit log
./fawkes-auth audit --limit 20

# Verify job submission still works
# (submit a test job)
```

#### Step 10: Monitor

```bash
# Monitor for authentication errors
./fawkes-auth audit --success false

# Check certificate expiration
./fawkes-auth cert verify
```

### Rolling Update (Zero Downtime)

For production systems requiring zero downtime:

1. **Update workers one at a time**:
   - Deploy auth database and certs to worker-01
   - Update worker-01 configuration
   - Restart worker-01
   - Verify worker-01 reconnects successfully
   - Repeat for remaining workers

2. **Update controller last**:
   - After all workers updated
   - Update controller configuration
   - Restart controller
   - Verify all workers reconnect

### Rollback Procedure

If migration fails:

```bash
# Stop all services
pkill -f fawkes

# Restore configurations
cp controller-config.yaml.backup controller-config.yaml
cp worker-config.yaml.backup worker-config.yaml

# Restore databases
cp ~/.fawkes/controller.db.backup ~/.fawkes/controller.db
cp ~/.fawkes/scheduler.db.backup ~/.fawkes/scheduler.db

# Restart services
./fawkes-worker --config worker-config.yaml &
./fawkes-controller --config controller-config.yaml
```

## Additional Resources

- **Fawkes Documentation**: See main README.md for general usage
- **Security Advisories**: Check GitHub releases for security updates
- **Bug Reports**: https://github.com/yourusername/fawkes/issues
- **OWASP Guidelines**: https://owasp.org/www-project-top-ten/

## Support

For issues or questions:
1. Check this documentation first
2. Review audit logs for clues
3. Enable DEBUG logging for detailed information
4. Open GitHub issue with logs and configuration (redact secrets!)
