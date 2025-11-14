#!/bin/bash

# Fawkes Authentication Test Suite
# Tests authentication, TLS, API keys, users, sessions, and permissions

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test database path
TEST_DB="/tmp/fawkes_auth_test_$$.db"
TEST_CERTS_DIR="/tmp/fawkes_certs_test_$$"

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up test artifacts..."
    rm -f "$TEST_DB" "$TEST_DB-journal"
    rm -rf "$TEST_CERTS_DIR"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Print functions
print_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

print_test() {
    echo -n "Testing: $1 ... "
    TESTS_RUN=$((TESTS_RUN + 1))
}

print_pass() {
    echo -e "${GREEN}PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_fail() {
    echo -e "${RED}FAIL${NC}"
    echo "  Error: $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_summary() {
    echo ""
    echo "=========================================="
    echo "Test Summary"
    echo "=========================================="
    echo "Total tests run: $TESTS_RUN"
    echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed: ${RED}$TESTS_FAILED${NC}"

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}All tests passed!${NC}"
        return 0
    else
        echo -e "\n${RED}Some tests failed!${NC}"
        return 1
    fi
}

# Check if fawkes-auth exists
check_fawkes_auth() {
    print_test "fawkes-auth executable exists"
    if [ -f "./fawkes-auth" ]; then
        print_pass
    else
        print_fail "fawkes-auth not found in current directory"
        exit 1
    fi
}

# Test database initialization
test_init() {
    print_header "Database Initialization Tests"

    print_test "Initialize authentication database"
    if echo -e "admin\nadmin@test.com\nTest Admin\nTestPass123!" | ./fawkes-auth init --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Database initialization failed"
        return 1
    fi

    print_test "Database file created"
    if [ -f "$TEST_DB" ]; then
        print_pass
    else
        print_fail "Database file not found"
        return 1
    fi

    print_test "Database contains users table"
    if sqlite3 "$TEST_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='users';" | grep -q "users"; then
        print_pass
    else
        print_fail "Users table not found"
        return 1
    fi

    print_test "Database contains api_keys table"
    if sqlite3 "$TEST_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys';" | grep -q "api_keys"; then
        print_pass
    else
        print_fail "API keys table not found"
        return 1
    fi

    print_test "Database contains sessions table"
    if sqlite3 "$TEST_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions';" | grep -q "sessions"; then
        print_pass
    else
        print_fail "Sessions table not found"
        return 1
    fi

    print_test "Database contains roles table"
    if sqlite3 "$TEST_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='roles';" | grep -q "roles"; then
        print_pass
    else
        print_fail "Roles table not found"
        return 1
    fi

    print_test "Database contains audit_log table"
    if sqlite3 "$TEST_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log';" | grep -q "audit_log"; then
        print_pass
    else
        print_fail "Audit log table not found"
        return 1
    fi

    print_test "Admin user created"
    if sqlite3 "$TEST_DB" "SELECT username FROM users WHERE username='admin';" | grep -q "admin"; then
        print_pass
    else
        print_fail "Admin user not created"
        return 1
    fi

    print_test "Admin user has admin role"
    if sqlite3 "$TEST_DB" "SELECT role FROM users WHERE username='admin';" | grep -q "admin"; then
        print_pass
    else
        print_fail "Admin user does not have admin role"
        return 1
    fi

    print_test "Default roles created"
    role_count=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM roles;")
    if [ "$role_count" -eq 4 ]; then
        print_pass
    else
        print_fail "Expected 4 default roles, found $role_count"
        return 1
    fi
}

# Test user management
test_users() {
    print_header "User Management Tests"

    print_test "Create operator user"
    if echo -e "OperatorPass123!" | ./fawkes-auth user add operator1 --email "op1@test.com" --full-name "Operator One" --role operator --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to create operator user"
        return 1
    fi

    print_test "Create viewer user"
    if echo -e "ViewerPass123!" | ./fawkes-auth user add viewer1 --email "viewer1@test.com" --full-name "Viewer One" --role viewer --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to create viewer user"
        return 1
    fi

    print_test "List users shows 3 users"
    user_count=$(./fawkes-auth user list --db-path "$TEST_DB" 2>/dev/null | grep -c "admin\|operator1\|viewer1")
    if [ "$user_count" -eq 3 ]; then
        print_pass
    else
        print_fail "Expected 3 users, found $user_count"
        return 1
    fi

    print_test "Disable user"
    if ./fawkes-auth user disable operator1 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to disable user"
        return 1
    fi

    print_test "User is disabled in database"
    if sqlite3 "$TEST_DB" "SELECT enabled FROM users WHERE username='operator1';" | grep -q "0"; then
        print_pass
    else
        print_fail "User not disabled in database"
        return 1
    fi

    print_test "Enable user"
    if ./fawkes-auth user enable operator1 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to enable user"
        return 1
    fi

    print_test "User is enabled in database"
    if sqlite3 "$TEST_DB" "SELECT enabled FROM users WHERE username='operator1';" | grep -q "1"; then
        print_pass
    else
        print_fail "User not enabled in database"
        return 1
    fi

    print_test "Change user password"
    if echo -e "NewOperatorPass123!" | ./fawkes-auth user passwd operator1 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to change password"
        return 1
    fi

    print_test "Delete user"
    if ./fawkes-auth user delete viewer1 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to delete user"
        return 1
    fi

    print_test "User removed from database"
    if ! sqlite3 "$TEST_DB" "SELECT username FROM users WHERE username='viewer1';" | grep -q "viewer1"; then
        print_pass
    else
        print_fail "User still in database after deletion"
        return 1
    fi
}

# Test API key management
test_api_keys() {
    print_header "API Key Management Tests"

    print_test "Create controller API key"
    output=$(./fawkes-auth key create controller-01 --type controller --db-path "$TEST_DB" 2>&1)
    if echo "$output" | grep -q "API Key created successfully"; then
        print_pass
    else
        print_fail "Failed to create controller API key"
        return 1
    fi

    print_test "API key displayed in output"
    if echo "$output" | grep -q "API Key:"; then
        print_pass
    else
        print_fail "API key not displayed in output"
        return 1
    fi

    print_test "Create worker API key"
    if ./fawkes-auth key create worker-01 --type worker --worker-id worker-01 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to create worker API key"
        return 1
    fi

    print_test "Create custom API key with permissions"
    if ./fawkes-auth key create custom-01 --type custom --permissions "job:read,worker:read" --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to create custom API key"
        return 1
    fi

    print_test "List API keys shows 3 keys"
    key_count=$(./fawkes-auth key list --db-path "$TEST_DB" 2>/dev/null | grep -c "controller-01\|worker-01\|custom-01")
    if [ "$key_count" -eq 3 ]; then
        print_pass
    else
        print_fail "Expected 3 API keys, found $key_count"
        return 1
    fi

    print_test "API key hash stored in database"
    if sqlite3 "$TEST_DB" "SELECT key_hash FROM api_keys WHERE key_name='controller-01';" | grep -q "."; then
        print_pass
    else
        print_fail "API key hash not found in database"
        return 1
    fi

    print_test "API key permissions stored correctly"
    perms=$(sqlite3 "$TEST_DB" "SELECT permissions FROM api_keys WHERE key_name='custom-01';")
    if echo "$perms" | grep -q "job:read" && echo "$perms" | grep -q "worker:read"; then
        print_pass
    else
        print_fail "API key permissions not stored correctly"
        return 1
    fi

    print_test "Revoke API key"
    if ./fawkes-auth key revoke 2 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to revoke API key"
        return 1
    fi

    print_test "API key disabled in database"
    if sqlite3 "$TEST_DB" "SELECT enabled FROM api_keys WHERE key_id=2;" | grep -q "0"; then
        print_pass
    else
        print_fail "API key not disabled in database"
        return 1
    fi

    print_test "Enable API key"
    if ./fawkes-auth key enable 2 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to enable API key"
        return 1
    fi

    print_test "Delete API key"
    if ./fawkes-auth key delete 3 --db-path "$TEST_DB" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to delete API key"
        return 1
    fi

    print_test "API key removed from database"
    if ! sqlite3 "$TEST_DB" "SELECT key_name FROM api_keys WHERE key_id=3;" | grep -q "custom-01"; then
        print_pass
    else
        print_fail "API key still in database after deletion"
        return 1
    fi
}

# Test TLS certificate generation
test_certificates() {
    print_header "TLS Certificate Tests"

    mkdir -p "$TEST_CERTS_DIR"

    print_test "Generate TLS certificates"
    if ./fawkes-auth cert generate --cert-file "$TEST_CERTS_DIR/test.crt" --key-file "$TEST_CERTS_DIR/test.key" --days 365 > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Failed to generate certificates"
        return 1
    fi

    print_test "Certificate file created"
    if [ -f "$TEST_CERTS_DIR/test.crt" ]; then
        print_pass
    else
        print_fail "Certificate file not found"
        return 1
    fi

    print_test "Private key file created"
    if [ -f "$TEST_CERTS_DIR/test.key" ]; then
        print_pass
    else
        print_fail "Private key file not found"
        return 1
    fi

    print_test "Certificate is valid X.509"
    if openssl x509 -in "$TEST_CERTS_DIR/test.crt" -noout -text > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Certificate is not valid X.509"
        return 1
    fi

    print_test "Private key is valid RSA"
    if openssl rsa -in "$TEST_CERTS_DIR/test.key" -check -noout > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Private key is not valid RSA"
        return 1
    fi

    print_test "Certificate matches private key"
    cert_modulus=$(openssl x509 -in "$TEST_CERTS_DIR/test.crt" -noout -modulus)
    key_modulus=$(openssl rsa -in "$TEST_CERTS_DIR/test.key" -noout -modulus)
    if [ "$cert_modulus" = "$key_modulus" ]; then
        print_pass
    else
        print_fail "Certificate and private key do not match"
        return 1
    fi

    print_test "Certificate validity period is ~365 days"
    # Check if certificate is valid for approximately 365 days (within 1 day tolerance)
    not_after=$(openssl x509 -in "$TEST_CERTS_DIR/test.crt" -noout -enddate | cut -d= -f2)
    not_after_epoch=$(date -d "$not_after" +%s)
    now_epoch=$(date +%s)
    days_valid=$(( ($not_after_epoch - $now_epoch) / 86400 ))

    if [ $days_valid -ge 364 ] && [ $days_valid -le 366 ]; then
        print_pass
    else
        print_fail "Certificate validity is $days_valid days, expected ~365"
        return 1
    fi

    print_test "Verify certificate command"
    if ./fawkes-auth cert verify --cert-file "$TEST_CERTS_DIR/test.crt" > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Certificate verification failed"
        return 1
    fi
}

# Test audit logging
test_audit() {
    print_header "Audit Logging Tests"

    print_test "Audit log contains initialization event"
    if ./fawkes-auth audit --db-path "$TEST_DB" 2>/dev/null | grep -q "system:init"; then
        print_pass
    else
        print_fail "Initialization event not in audit log"
        return 1
    fi

    print_test "Audit log contains user creation events"
    if ./fawkes-auth audit --db-path "$TEST_DB" 2>/dev/null | grep -q "user:create"; then
        print_pass
    else
        print_fail "User creation events not in audit log"
        return 1
    fi

    print_test "Audit log contains API key creation events"
    if ./fawkes-auth audit --db-path "$TEST_DB" 2>/dev/null | grep -q "apikey:create"; then
        print_pass
    else
        print_fail "API key creation events not in audit log"
        return 1
    fi

    print_test "Filter audit log by action"
    if ./fawkes-auth audit --action "user:create" --db-path "$TEST_DB" 2>/dev/null | grep -q "user:create"; then
        print_pass
    else
        print_fail "Failed to filter audit log by action"
        return 1
    fi

    print_test "Audit log contains timestamps"
    if ./fawkes-auth audit --limit 5 --db-path "$TEST_DB" 2>/dev/null | grep -q "[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}"; then
        print_pass
    else
        print_fail "Audit log entries missing timestamps"
        return 1
    fi
}

# Test Python authentication library
test_python_auth() {
    print_header "Python Authentication Library Tests"

    # Create test Python script
    cat > /tmp/test_auth_$$.py << 'EOF'
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fawkes.db.auth_db import AuthDB
from fawkes.auth.middleware import authenticate_request, add_authentication, AuthenticationError

# Test database path from environment
db_path = os.environ.get('TEST_DB')
auth_db = AuthDB(db_path)

# Test 1: Password hashing
print("TEST: Password hashing")
password_hash, salt = auth_db.hash_password("TestPassword123!")
assert len(password_hash) == 64, "Password hash should be 64 chars (SHA256)"
assert len(salt) == 64, "Salt should be 64 chars"
print("PASS")

# Test 2: Verify password
print("TEST: Password verification")
password_hash2, _ = auth_db.hash_password("TestPassword123!", salt)
assert password_hash == password_hash2, "Same password with same salt should produce same hash"
print("PASS")

# Test 3: Create API key
print("TEST: Create API key")
api_key, key_id = auth_db.create_api_key("test-key", "controller")
assert len(api_key) > 0, "API key should be generated"
assert key_id > 0, "Key ID should be returned"
print("PASS")

# Test 4: Validate API key
print("TEST: Validate API key")
principal = auth_db.validate_api_key(api_key)
assert principal is not None, "API key should validate"
assert "permissions" in principal, "Principal should have permissions"
print("PASS")

# Test 5: Validate invalid API key
print("TEST: Invalid API key rejection")
try:
    auth_db.validate_api_key("invalid-key-12345")
    print("FAIL: Should have raised exception for invalid key")
    sys.exit(1)
except Exception:
    print("PASS")

# Test 6: Add authentication to message
print("TEST: Add authentication to message")
message = {"type": "TEST"}
auth_message = add_authentication(message, "api_key", api_key)
assert "auth_type" in auth_message, "Auth type should be added"
assert "api_key" in auth_message, "API key should be added"
assert auth_message["auth_type"] == "api_key", "Auth type should be api_key"
print("PASS")

# Test 7: Authenticate request
print("TEST: Authenticate request")
principal = authenticate_request(auth_db, auth_message)
assert principal is not None, "Request should authenticate"
assert "permissions" in principal, "Principal should have permissions"
print("PASS")

# Test 8: Authenticate invalid request
print("TEST: Invalid request rejection")
try:
    invalid_message = {"type": "TEST", "auth_type": "api_key", "api_key": "invalid"}
    authenticate_request(auth_db, invalid_message)
    print("FAIL: Should have raised AuthenticationError")
    sys.exit(1)
except AuthenticationError:
    print("PASS")

# Test 9: User authentication
print("TEST: User authentication")
success = auth_db.authenticate_user("admin", "TestPass123!", "127.0.0.1", "test-agent")
assert success is not None, "Admin user should authenticate"
print("PASS")

# Test 10: Failed login tracking
print("TEST: Failed login tracking")
# Try invalid password multiple times
for i in range(3):
    try:
        auth_db.authenticate_user("admin", "WrongPassword", "127.0.0.1", "test-agent")
    except Exception:
        pass

# Check failed attempts were recorded
cursor = auth_db._conn.execute(
    "SELECT failed_login_attempts FROM users WHERE username = ?",
    ("admin",)
)
failed_attempts = cursor.fetchone()[0]
assert failed_attempts >= 3, f"Should have at least 3 failed attempts, got {failed_attempts}"
print("PASS")

auth_db.close()
print("\nAll Python authentication tests passed!")
EOF

    print_test "Python authentication library tests"
    if TEST_DB="$TEST_DB" python3 /tmp/test_auth_$$.py > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Python authentication library tests failed"
        TEST_DB="$TEST_DB" python3 /tmp/test_auth_$$.py
        return 1
    fi

    rm -f /tmp/test_auth_$$.py
}

# Test TLS integration
test_tls_integration() {
    print_header "TLS Integration Tests"

    # Create test Python script for TLS
    cat > /tmp/test_tls_$$.py << 'EOF'
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fawkes.auth.tls import create_ssl_context, ensure_certificates, generate_self_signed_cert

# Test 1: Ensure certificates (auto-generate)
print("TEST: Ensure certificates (auto-generate)")
cert_dir = os.environ.get('TEST_CERTS_DIR')
cert_file = os.path.join(cert_dir, "auto.crt")
key_file = os.path.join(cert_dir, "auto.key")

cert, key = ensure_certificates(cert_file, key_file)
assert os.path.exists(cert), f"Certificate should be created at {cert}"
assert os.path.exists(key), f"Key should be created at {key}"
print("PASS")

# Test 2: Ensure certificates (existing)
print("TEST: Ensure certificates (existing)")
cert2, key2 = ensure_certificates(cert_file, key_file)
assert cert2 == cert, "Should return same certificate path"
assert key2 == key, "Should return same key path"
print("PASS")

# Test 3: Create SSL context (server)
print("TEST: Create SSL context (server)")
ssl_context = create_ssl_context(cert_file=cert, key_file=key, is_server=True)
assert ssl_context is not None, "SSL context should be created"
assert hasattr(ssl_context, 'wrap_socket'), "SSL context should have wrap_socket method"
print("PASS")

# Test 4: Create SSL context (client)
print("TEST: Create SSL context (client)")
ssl_context = create_ssl_context(cert_file=cert, key_file=key, is_server=False)
assert ssl_context is not None, "SSL context should be created"
assert hasattr(ssl_context, 'wrap_socket'), "SSL context should have wrap_socket method"
print("PASS")

# Test 5: Generate self-signed cert with custom validity
print("TEST: Generate self-signed cert with custom validity")
custom_cert = os.path.join(cert_dir, "custom.crt")
custom_key = os.path.join(cert_dir, "custom.key")
generate_self_signed_cert(custom_cert, custom_key, days_valid=730)
assert os.path.exists(custom_cert), "Custom certificate should be created"
assert os.path.exists(custom_key), "Custom key should be created"
print("PASS")

print("\nAll TLS integration tests passed!")
EOF

    print_test "TLS integration tests"
    if TEST_CERTS_DIR="$TEST_CERTS_DIR" python3 /tmp/test_tls_$$.py > /dev/null 2>&1; then
        print_pass
    else
        print_fail "TLS integration tests failed"
        TEST_CERTS_DIR="$TEST_CERTS_DIR" python3 /tmp/test_tls_$$.py
        return 1
    fi

    rm -f /tmp/test_tls_$$.py
}

# Test permission system
test_permissions() {
    print_header "Permission System Tests"

    # Create test Python script for permissions
    cat > /tmp/test_perms_$$.py << 'EOF'
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fawkes.db.auth_db import AuthDB
from fawkes.auth.middleware import require_permission, AuthorizationError

db_path = os.environ.get('TEST_DB')
auth_db = AuthDB(db_path)

# Test 1: Check admin has all permissions
print("TEST: Admin has all permissions")
admin_perms = auth_db.get_role_permissions("admin")
assert "job:create" in admin_perms, "Admin should have job:create"
assert "user:create" in admin_perms, "Admin should have user:create"
assert "worker:manage" in admin_perms, "Admin should have worker:manage"
print("PASS")

# Test 2: Check operator permissions
print("TEST: Operator has correct permissions")
operator_perms = auth_db.get_role_permissions("operator")
assert "job:create" in operator_perms, "Operator should have job:create"
assert "user:create" not in operator_perms, "Operator should NOT have user:create"
print("PASS")

# Test 3: Check viewer permissions
print("TEST: Viewer has correct permissions")
viewer_perms = auth_db.get_role_permissions("viewer")
assert "job:read" in viewer_perms, "Viewer should have job:read"
assert "job:create" not in viewer_perms, "Viewer should NOT have job:create"
print("PASS")

# Test 4: Check worker permissions
print("TEST: Worker has correct permissions")
worker_perms = auth_db.get_role_permissions("worker")
assert "worker:register" in worker_perms, "Worker should have worker:register"
assert "job:create" not in worker_perms, "Worker should NOT have job:create"
print("PASS")

# Test 5: Require permission (authorized)
print("TEST: Require permission (authorized)")
admin_principal = {"permissions": admin_perms}
try:
    require_permission(admin_principal, "job:create")
    print("PASS")
except AuthorizationError:
    print("FAIL: Admin should have job:create permission")
    sys.exit(1)

# Test 6: Require permission (unauthorized)
print("TEST: Require permission (unauthorized)")
viewer_principal = {"permissions": viewer_perms}
try:
    require_permission(viewer_principal, "job:create")
    print("FAIL: Viewer should NOT have job:create permission")
    sys.exit(1)
except AuthorizationError:
    print("PASS")

auth_db.close()
print("\nAll permission tests passed!")
EOF

    print_test "Permission system tests"
    if TEST_DB="$TEST_DB" python3 /tmp/test_perms_$$.py > /dev/null 2>&1; then
        print_pass
    else
        print_fail "Permission system tests failed"
        TEST_DB="$TEST_DB" python3 /tmp/test_perms_$$.py
        return 1
    fi

    rm -f /tmp/test_perms_$$.py
}

# Main test execution
main() {
    echo "=========================================="
    echo "Fawkes Authentication Test Suite"
    echo "=========================================="
    echo "Test database: $TEST_DB"
    echo "Test certs dir: $TEST_CERTS_DIR"

    # Run all test suites
    check_fawkes_auth
    test_init
    test_users
    test_api_keys
    test_certificates
    test_audit
    test_python_auth
    test_tls_integration
    test_permissions

    # Print summary and exit with appropriate code
    print_summary
    exit $?
}

# Run main
main
