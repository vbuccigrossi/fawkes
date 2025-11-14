"""
Fawkes Authentication Database

Manages users, API keys, roles, and permissions for secure access control.
"""

import sqlite3
import hashlib
import secrets
import time
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger("fawkes.auth.db")


class AuthDB:
    """Authentication and authorization database"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.create_tables()

    def create_tables(self):
        """Create authentication tables"""
        cursor = self.conn.cursor()

        # Users table
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            email TEXT,
            full_name TEXT,
            role TEXT NOT NULL DEFAULT 'viewer',
            enabled BOOLEAN DEFAULT 1,
            created_at INTEGER,
            last_login INTEGER,
            password_changed_at INTEGER,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until INTEGER
        )''')

        # API keys table (for worker authentication)
        cursor.execute('''CREATE TABLE IF NOT EXISTS api_keys (
            key_id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            key_name TEXT NOT NULL,
            key_type TEXT NOT NULL,
            created_by INTEGER,
            worker_id TEXT,
            enabled BOOLEAN DEFAULT 1,
            created_at INTEGER,
            expires_at INTEGER,
            last_used_at INTEGER,
            permissions TEXT,
            FOREIGN KEY (created_by) REFERENCES users(user_id)
        )''')

        # Sessions table (for active user sessions)
        cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            created_at INTEGER,
            expires_at INTEGER,
            last_activity INTEGER,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )''')

        # Roles table
        cursor.execute('''CREATE TABLE IF NOT EXISTS roles (
            role_name TEXT PRIMARY KEY,
            description TEXT,
            permissions TEXT,
            created_at INTEGER
        )''')

        # Audit log table
        cursor.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,
            user_id INTEGER,
            action TEXT NOT NULL,
            resource TEXT,
            details TEXT,
            ip_address TEXT,
            success BOOLEAN,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )''')

        # Indices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)')

        self.conn.commit()

        # Initialize default roles if not exists
        self._initialize_default_roles()
        logger.debug("Authentication database tables created/verified")

    def _initialize_default_roles(self):
        """Initialize default roles"""
        cursor = self.conn.cursor()

        default_roles = {
            "admin": {
                "description": "Full system access",
                "permissions": [
                    "user:create", "user:read", "user:update", "user:delete",
                    "api_key:create", "api_key:read", "api_key:revoke",
                    "job:create", "job:read", "job:update", "job:delete",
                    "worker:register", "worker:read", "worker:update", "worker:delete",
                    "campaign:create", "campaign:read", "campaign:delete",
                    "crash:read", "crash:triage", "crash:delete",
                    "system:configure", "system:shutdown"
                ]
            },
            "operator": {
                "description": "Can manage jobs and workers",
                "permissions": [
                    "user:read",
                    "api_key:read",
                    "job:create", "job:read", "job:update", "job:delete",
                    "worker:read", "worker:update",
                    "campaign:create", "campaign:read",
                    "crash:read", "crash:triage"
                ]
            },
            "viewer": {
                "description": "Read-only access",
                "permissions": [
                    "user:read",
                    "job:read",
                    "worker:read",
                    "campaign:read",
                    "crash:read"
                ]
            },
            "worker": {
                "description": "Worker node permissions",
                "permissions": [
                    "job:read", "job:update",
                    "worker:update"
                ]
            }
        }

        for role_name, role_info in default_roles.items():
            cursor.execute('SELECT role_name FROM roles WHERE role_name = ?', (role_name,))
            if not cursor.fetchone():
                cursor.execute('''INSERT INTO roles (role_name, description, permissions, created_at)
                                 VALUES (?, ?, ?, ?)''', (
                    role_name,
                    role_info["description"],
                    json.dumps(role_info["permissions"]),
                    int(time.time())
                ))

        self.conn.commit()

    def hash_password(self, password: str, salt: Optional[str] = None) -> tuple:
        """
        Hash a password with salt

        Args:
            password: Plain text password
            salt: Optional salt (generated if not provided)

        Returns:
            Tuple of (password_hash, salt)
        """
        if salt is None:
            salt = secrets.token_hex(32)

        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # iterations
        ).hex()

        return password_hash, salt

    def create_user(self, username: str, password: str, role: str = "viewer",
                   email: Optional[str] = None, full_name: Optional[str] = None) -> int:
        """
        Create a new user

        Args:
            username: Unique username
            password: Plain text password (will be hashed)
            role: User role (admin, operator, viewer)
            email: Optional email
            full_name: Optional full name

        Returns:
            User ID
        """
        cursor = self.conn.cursor()

        # Validate role exists
        cursor.execute('SELECT role_name FROM roles WHERE role_name = ?', (role,))
        if not cursor.fetchone():
            raise ValueError(f"Invalid role: {role}")

        # Hash password
        password_hash, salt = self.hash_password(password)

        cursor.execute('''INSERT INTO users (username, password_hash, salt, email, full_name,
                         role, created_at, password_changed_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
            username,
            password_hash,
            salt,
            email,
            full_name,
            role,
            int(time.time()),
            int(time.time())
        ))

        user_id = cursor.lastrowid
        self.conn.commit()

        self.audit_log(user_id, "user_created", f"user:{user_id}",
                      {"username": username, "role": role}, success=True)

        logger.info(f"Created user: {username} (role: {role})")
        return user_id

    def authenticate_user(self, username: str, password: str,
                         ip_address: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Authenticate a user with username and password

        Args:
            username: Username
            password: Plain text password
            ip_address: Optional IP address for audit logging

        Returns:
            User dict if authenticated, None otherwise
        """
        cursor = self.conn.cursor()

        cursor.execute('''SELECT user_id, password_hash, salt, role, enabled,
                         locked_until, failed_login_attempts
                         FROM users WHERE username = ?''', (username,))
        row = cursor.fetchone()

        if not row:
            self.audit_log(None, "login_failed", f"user:{username}",
                          {"reason": "user_not_found"}, ip_address=ip_address, success=False)
            return None

        user_id, stored_hash, salt, role, enabled, locked_until, failed_attempts = row

        # Check if account is locked
        if locked_until and locked_until > time.time():
            self.audit_log(user_id, "login_failed", f"user:{user_id}",
                          {"reason": "account_locked"}, ip_address=ip_address, success=False)
            return None

        # Check if account is enabled
        if not enabled:
            self.audit_log(user_id, "login_failed", f"user:{user_id}",
                          {"reason": "account_disabled"}, ip_address=ip_address, success=False)
            return None

        # Verify password
        password_hash, _ = self.hash_password(password, salt)

        if password_hash != stored_hash:
            # Increment failed attempts
            failed_attempts += 1
            locked_until_time = None

            # Lock account after 5 failed attempts for 15 minutes
            if failed_attempts >= 5:
                locked_until_time = int(time.time()) + 900  # 15 minutes

            cursor.execute('''UPDATE users SET failed_login_attempts = ?,
                             locked_until = ? WHERE user_id = ?''',
                          (failed_attempts, locked_until_time, user_id))
            self.conn.commit()

            self.audit_log(user_id, "login_failed", f"user:{user_id}",
                          {"reason": "invalid_password", "failed_attempts": failed_attempts},
                          ip_address=ip_address, success=False)
            return None

        # Successful login - reset failed attempts and update last login
        cursor.execute('''UPDATE users SET failed_login_attempts = 0,
                         locked_until = NULL, last_login = ?
                         WHERE user_id = ?''', (int(time.time()), user_id))
        self.conn.commit()

        self.audit_log(user_id, "login_success", f"user:{user_id}",
                      {}, ip_address=ip_address, success=True)

        # Get user permissions
        cursor.execute('SELECT permissions FROM roles WHERE role_name = ?', (role,))
        permissions_row = cursor.fetchone()
        permissions = json.loads(permissions_row[0]) if permissions_row else []

        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "permissions": permissions
        }

    def create_api_key(self, key_name: str, key_type: str = "worker",
                      created_by: Optional[int] = None, worker_id: Optional[str] = None,
                      permissions: Optional[List[str]] = None,
                      expires_days: Optional[int] = None) -> str:
        """
        Create a new API key

        Args:
            key_name: Descriptive name for the key
            key_type: Type of key (worker, service, user)
            created_by: User ID who created the key
            worker_id: Optional worker ID this key is for
            permissions: Optional list of permissions (defaults to worker role)
            expires_days: Optional expiration in days

        Returns:
            Plain text API key (only returned once)
        """
        cursor = self.conn.cursor()

        # Generate API key
        api_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Default permissions for worker keys
        if permissions is None:
            if key_type == "worker":
                cursor.execute('SELECT permissions FROM roles WHERE role_name = ?', ('worker',))
                row = cursor.fetchone()
                permissions = json.loads(row[0]) if row else []

        expires_at = None
        if expires_days:
            expires_at = int(time.time()) + (expires_days * 86400)

        cursor.execute('''INSERT INTO api_keys (key_hash, key_name, key_type, created_by,
                         worker_id, created_at, expires_at, permissions)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
            key_hash,
            key_name,
            key_type,
            created_by,
            worker_id,
            int(time.time()),
            expires_at,
            json.dumps(permissions) if permissions else None
        ))

        key_id = cursor.lastrowid
        self.conn.commit()

        self.audit_log(created_by, "api_key_created", f"api_key:{key_id}",
                      {"key_name": key_name, "key_type": key_type}, success=True)

        logger.info(f"Created API key: {key_name} (type: {key_type})")
        return api_key

    def validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Validate an API key

        Args:
            api_key: Plain text API key

        Returns:
            Dict with key info and permissions if valid, None otherwise
        """
        cursor = self.conn.cursor()

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        cursor.execute('''SELECT key_id, key_name, key_type, worker_id, enabled,
                         expires_at, permissions
                         FROM api_keys WHERE key_hash = ?''', (key_hash,))
        row = cursor.fetchone()

        if not row:
            return None

        key_id, key_name, key_type, worker_id, enabled, expires_at, permissions_json = row

        # Check if key is enabled
        if not enabled:
            return None

        # Check if key is expired
        if expires_at and expires_at < time.time():
            return None

        # Update last used timestamp
        cursor.execute('UPDATE api_keys SET last_used_at = ? WHERE key_id = ?',
                      (int(time.time()), key_id))
        self.conn.commit()

        permissions = json.loads(permissions_json) if permissions_json else []

        return {
            "key_id": key_id,
            "key_name": key_name,
            "key_type": key_type,
            "worker_id": worker_id,
            "permissions": permissions
        }

    def create_session(self, user_id: int, ip_address: Optional[str] = None,
                      user_agent: Optional[str] = None, expires_hours: int = 24) -> str:
        """
        Create a new session token

        Args:
            user_id: User ID
            ip_address: Optional client IP address
            user_agent: Optional user agent string
            expires_hours: Session expiration in hours (default: 24)

        Returns:
            Session token
        """
        cursor = self.conn.cursor()

        session_id = secrets.token_urlsafe(16)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        now = int(time.time())
        expires_at = now + (expires_hours * 3600)

        cursor.execute('''INSERT INTO sessions (session_id, user_id, token_hash,
                         created_at, expires_at, last_activity, ip_address, user_agent)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
            session_id,
            user_id,
            token_hash,
            now,
            expires_at,
            now,
            ip_address,
            user_agent
        ))

        self.conn.commit()
        return token

    def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a session token

        Args:
            token: Session token

        Returns:
            Dict with user info if valid, None otherwise
        """
        cursor = self.conn.cursor()

        token_hash = hashlib.sha256(token.encode()).hexdigest()

        cursor.execute('''SELECT s.session_id, s.user_id, s.expires_at,
                         u.username, u.role, r.permissions
                         FROM sessions s
                         JOIN users u ON s.user_id = u.user_id
                         JOIN roles r ON u.role = r.role_name
                         WHERE s.token_hash = ?''', (token_hash,))
        row = cursor.fetchone()

        if not row:
            return None

        session_id, user_id, expires_at, username, role, permissions_json = row

        # Check if session is expired
        if expires_at < time.time():
            self.delete_session(session_id)
            return None

        # Update last activity
        cursor.execute('UPDATE sessions SET last_activity = ? WHERE session_id = ?',
                      (int(time.time()), session_id))
        self.conn.commit()

        permissions = json.loads(permissions_json) if permissions_json else []

        return {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "role": role,
            "permissions": permissions
        }

    def delete_session(self, session_id: str):
        """Delete a session"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        self.conn.commit()

    def audit_log(self, user_id: Optional[int], action: str, resource: str,
                 details: Optional[Dict] = None, ip_address: Optional[str] = None,
                 success: bool = True):
        """
        Log an audit event

        Args:
            user_id: User ID (None for system actions)
            action: Action performed
            resource: Resource affected
            details: Optional additional details
            ip_address: Optional IP address
            success: Whether the action succeeded
        """
        cursor = self.conn.cursor()

        cursor.execute('''INSERT INTO audit_log (timestamp, user_id, action, resource,
                         details, ip_address, success)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''', (
            int(time.time()),
            user_id,
            action,
            resource,
            json.dumps(details) if details else None,
            ip_address,
            success
        ))

        self.conn.commit()

    def get_user(self, user_id: Optional[int] = None,
                username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get user information"""
        cursor = self.conn.cursor()

        if user_id:
            cursor.execute('''SELECT user_id, username, email, full_name, role, enabled,
                             created_at, last_login FROM users WHERE user_id = ?''', (user_id,))
        elif username:
            cursor.execute('''SELECT user_id, username, email, full_name, role, enabled,
                             created_at, last_login FROM users WHERE username = ?''', (username,))
        else:
            return None

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "email": row[2],
            "full_name": row[3],
            "role": row[4],
            "enabled": bool(row[5]),
            "created_at": row[6],
            "last_login": row[7]
        }

    def list_users(self) -> List[Dict[str, Any]]:
        """List all users"""
        cursor = self.conn.cursor()
        cursor.execute('''SELECT user_id, username, email, full_name, role, enabled,
                         created_at, last_login FROM users ORDER BY username''')

        users = []
        for row in cursor.fetchall():
            users.append({
                "user_id": row[0],
                "username": row[1],
                "email": row[2],
                "full_name": row[3],
                "role": row[4],
                "enabled": bool(row[5]),
                "created_at": row[6],
                "last_login": row[7]
            })

        return users

    def list_api_keys(self, created_by: Optional[int] = None) -> List[Dict[str, Any]]:
        """List API keys"""
        cursor = self.conn.cursor()

        if created_by:
            cursor.execute('''SELECT key_id, key_name, key_type, worker_id, enabled,
                             created_at, expires_at, last_used_at
                             FROM api_keys WHERE created_by = ? ORDER BY created_at DESC''',
                          (created_by,))
        else:
            cursor.execute('''SELECT key_id, key_name, key_type, worker_id, enabled,
                             created_at, expires_at, last_used_at
                             FROM api_keys ORDER BY created_at DESC''')

        keys = []
        for row in cursor.fetchall():
            keys.append({
                "key_id": row[0],
                "key_name": row[1],
                "key_type": row[2],
                "worker_id": row[3],
                "enabled": bool(row[4]),
                "created_at": row[5],
                "expires_at": row[6],
                "last_used_at": row[7]
            })

        return keys

    def revoke_api_key(self, key_id: int, revoked_by: Optional[int] = None):
        """Revoke an API key"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE api_keys SET enabled = 0 WHERE key_id = ?', (key_id,))
        self.conn.commit()

        self.audit_log(revoked_by, "api_key_revoked", f"api_key:{key_id}", success=True)
        logger.info(f"Revoked API key: {key_id}")

    def change_password(self, user_id: int, new_password: str):
        """Change user password"""
        cursor = self.conn.cursor()

        password_hash, salt = self.hash_password(new_password)

        cursor.execute('''UPDATE users SET password_hash = ?, salt = ?,
                         password_changed_at = ? WHERE user_id = ?''',
                      (password_hash, salt, int(time.time()), user_id))
        self.conn.commit()

        self.audit_log(user_id, "password_changed", f"user:{user_id}", success=True)
        logger.info(f"Changed password for user ID: {user_id}")

    def set_user_role(self, user_id: int, role: str, changed_by: Optional[int] = None):
        """Change user role"""
        cursor = self.conn.cursor()

        # Validate role exists
        cursor.execute('SELECT role_name FROM roles WHERE role_name = ?', (role,))
        if not cursor.fetchone():
            raise ValueError(f"Invalid role: {role}")

        cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
        self.conn.commit()

        self.audit_log(changed_by, "user_role_changed", f"user:{user_id}",
                      {"new_role": role}, success=True)
        logger.info(f"Changed role for user ID {user_id} to: {role}")

    def enable_user(self, user_id: int, enabled_by: Optional[int] = None):
        """Enable a user account"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET enabled = 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()

        self.audit_log(enabled_by, "user_enabled", f"user:{user_id}", success=True)

    def disable_user(self, user_id: int, disabled_by: Optional[int] = None):
        """Disable a user account"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET enabled = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()

        self.audit_log(disabled_by, "user_disabled", f"user:{user_id}", success=True)

    def get_audit_log(self, user_id: Optional[int] = None,
                     action: Optional[str] = None,
                     limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit log entries"""
        cursor = self.conn.cursor()

        query = 'SELECT log_id, timestamp, user_id, action, resource, details, ip_address, success FROM audit_log WHERE 1=1'
        params = []

        if user_id:
            query += ' AND user_id = ?'
            params.append(user_id)

        if action:
            query += ' AND action = ?'
            params.append(action)

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)

        logs = []
        for row in cursor.fetchall():
            logs.append({
                "log_id": row[0],
                "timestamp": row[1],
                "user_id": row[2],
                "action": row[3],
                "resource": row[4],
                "details": json.loads(row[5]) if row[5] else {},
                "ip_address": row[6],
                "success": bool(row[7])
            })

        return logs

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
