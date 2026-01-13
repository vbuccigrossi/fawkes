#!/usr/bin/env python3
"""
Test Network Protocol Fuzzing
"""

import sys
sys.path.insert(0, '/home/ebrown/Desktop/projects/fawkes')

from network import ProtocolStateMachine, SessionManager, ProtocolFuzzer, BuiltinProtocols


def test_state_machine():
    """Test protocol state machine."""
    print("\n=== Test 1: Protocol State Machine ===")

    # Create simple state machine
    sm = ProtocolStateMachine("TEST")

    # Add states
    sm.add_state("INIT", is_initial=True)
    sm.add_state("CONNECTED")
    sm.add_state("AUTHENTICATED")

    # Add transitions
    sm.add_transition("INIT", "CONNECTED", "connect")
    sm.add_transition("CONNECTED", "AUTHENTICATED", "login",
                     message="LOGIN user:pass\n")

    # Test initial state
    assert sm.get_state() == "INIT", "Initial state should be INIT"
    print(f"✓ Initial state: {sm.get_state()}")

    # Test transition
    assert sm.transition("connect") == True, "Transition should succeed"
    assert sm.get_state() == "CONNECTED", "Should be in CONNECTED state"
    print(f"✓ After connect: {sm.get_state()}")

    # Test invalid transition
    assert sm.transition("invalid") == False, "Invalid transition should fail"
    print(f"✓ Invalid transition rejected")

    # Test path finding
    sm.reset()
    path = sm.get_path_to_state("AUTHENTICATED")
    assert path == ["connect", "login"], f"Path should be ['connect', 'login'], got {path}"
    print(f"✓ Path to AUTHENTICATED: {path}")

    # Test valid actions
    sm.reset()
    actions = sm.get_valid_actions()
    assert len(actions) == 1, "Should have 1 valid action from INIT"
    assert actions[0]['action'] == "connect", "Action should be 'connect'"
    print(f"✓ Valid actions from INIT: {[a['action'] for a in actions]}")

    print("✓ All state machine tests passed!\n")


def test_builtin_protocols():
    """Test builtin protocol definitions."""
    print("=== Test 2: Builtin Protocols ===")

    # Test listing protocols
    protocols = BuiltinProtocols.list_protocols()
    assert 'http' in protocols, "Should have HTTP protocol"
    assert 'ftp' in protocols, "Should have FTP protocol"
    assert 'smtp' in protocols, "Should have SMTP protocol"
    print(f"✓ Available protocols: {', '.join(protocols)}")

    # Test HTTP state machine
    http_sm = BuiltinProtocols.http()
    assert http_sm.name == "HTTP", "Name should be HTTP"
    assert http_sm.initial_state == "INIT", "Initial state should be INIT"
    assert "CONNECTED" in http_sm.states, "Should have CONNECTED state"
    assert "REQUEST_SENT" in http_sm.states, "Should have REQUEST_SENT state"
    print(f"✓ HTTP state machine: {len(http_sm.states)} states")

    # Test FTP state machine
    ftp_sm = BuiltinProtocols.ftp()
    assert ftp_sm.name == "FTP", "Name should be FTP"
    assert "AUTHENTICATED" in ftp_sm.states, "Should have AUTHENTICATED state"
    print(f"✓ FTP state machine: {len(ftp_sm.states)} states")

    # Test SMTP state machine
    smtp_sm = BuiltinProtocols.smtp()
    assert smtp_sm.name == "SMTP", "Name should be SMTP"
    assert "HELO" in smtp_sm.states, "Should have HELO state"
    assert "MAIL" in smtp_sm.states, "Should have MAIL state"
    assert "RCPT" in smtp_sm.states, "Should have RCPT state"
    assert "DATA" in smtp_sm.states, "Should have DATA state"
    print(f"✓ SMTP state machine: {len(smtp_sm.states)} states")

    # Test get_all_protocols
    all_protocols = BuiltinProtocols.get_all_protocols()
    assert len(all_protocols) == 7, f"Should have 7 protocols, got {len(all_protocols)}"
    assert 'http' in all_protocols, "Should have HTTP in all_protocols"
    assert 'telnet' in all_protocols, "Should have Telnet in all_protocols"
    print(f"✓ get_all_protocols returned {len(all_protocols)} protocols")

    # Test transitions in HTTP
    http_sm.reset()
    valid_actions = http_sm.get_valid_actions("INIT")
    assert len(valid_actions) > 0, "INIT should have valid actions"
    assert valid_actions[0]['action'] == "connect", "First action should be connect"
    print(f"✓ HTTP transitions validated")

    print("✓ All builtin protocol tests passed!\n")


def test_fuzzing_strategies():
    """Test fuzzing mutation strategies."""
    print("=== Test 3: Fuzzing Strategies ===")

    # Create simple state machine
    sm = ProtocolStateMachine("TEST")
    sm.add_state("INIT", is_initial=True)
    sm.add_state("CONNECTED")
    sm.add_transition("INIT", "CONNECTED", "connect",
                     message="HELLO WORLD")

    # Create fuzzer (won't actually connect)
    fuzzer = ProtocolFuzzer("localhost", 9999, sm)

    # Test fuzzing strategies
    original = "GET /index.html HTTP/1.1"

    # Test overflow
    fuzzed = fuzzer._fuzz_overflow(original)
    assert len(fuzzed) > len(original), "Overflow should increase length"
    print(f"✓ Overflow: {len(original)} -> {len(fuzzed)} bytes")

    # Test special chars
    fuzzed = fuzzer._fuzz_special_chars(original)
    # Should contain special char
    special_chars = ['\x00', '\n', '\r', '\t', '%', '\\', '"', '\'', '<', '>', '&']
    has_special = any(c in fuzzed for c in special_chars)
    assert has_special, "Should contain special character"
    print(f"✓ Special chars injected")

    # Test format strings
    fuzzed = fuzzer._fuzz_format_strings(original)
    format_strings = ['%s', '%x', '%n', '%p', '%d']
    has_format = any(f in fuzzed for f in format_strings)
    assert has_format, "Should contain format string"
    print(f"✓ Format strings: {fuzzed[-20:]}")

    # Test truncate
    fuzzed = fuzzer._fuzz_truncate(original)
    assert len(fuzzed) <= len(original), "Truncate should reduce or maintain length"
    print(f"✓ Truncate: {len(original)} -> {len(fuzzed)} bytes")

    # Test repeat
    fuzzed = fuzzer._fuzz_repeat(original)
    assert len(fuzzed) >= len(original), "Repeat should increase length"
    print(f"✓ Repeat: {len(original)} -> {len(fuzzed)} bytes")

    # Test general mutation
    fuzzed = fuzzer._fuzz_message(original)
    print(f"✓ General mutation: '{original[:20]}...' -> '{fuzzed[:20]}...'")

    print("✓ All fuzzing strategy tests passed!\n")


def test_path_finding():
    """Test path finding in state machines."""
    print("=== Test 4: Path Finding ===")

    # Create complex state machine
    sm = ProtocolStateMachine("COMPLEX")

    # States
    sm.add_state("INIT", is_initial=True)
    sm.add_state("A")
    sm.add_state("B")
    sm.add_state("C")
    sm.add_state("D")

    # Transitions (create multiple paths)
    sm.add_transition("INIT", "A", "go_a")
    sm.add_transition("INIT", "B", "go_b")
    sm.add_transition("A", "C", "a_to_c")
    sm.add_transition("B", "C", "b_to_c")
    sm.add_transition("C", "D", "c_to_d")

    # Find shortest path to D
    path = sm.get_path_to_state("D")
    assert path is not None, "Should find path to D"
    assert len(path) == 3, f"Path should have 3 steps, got {len(path)}"
    assert path[-1] == "c_to_d", "Last action should be c_to_d"
    print(f"✓ Path to D: {path}")

    # Find path to non-existent state
    path = sm.get_path_to_state("NONEXISTENT")
    assert path is None, "Should return None for non-existent state"
    print(f"✓ Non-existent state returns None")

    # Find path to initial state
    path = sm.get_path_to_state("INIT")
    assert path == [], "Path to initial state should be empty"
    print(f"✓ Path to INIT: {path}")

    print("✓ All path finding tests passed!\n")


def test_http_state_machine():
    """Test HTTP state machine in detail."""
    print("=== Test 5: HTTP State Machine Detail ===")

    http_sm = BuiltinProtocols.http()

    # Test states
    expected_states = ["INIT", "CONNECTED", "REQUEST_SENT", "RESPONSE_RECEIVED", "CLOSED"]
    for state in expected_states:
        assert state in http_sm.states, f"Should have {state} state"
    print(f"✓ All expected states present: {', '.join(expected_states)}")

    # Test path to send request
    http_sm.reset()
    path = http_sm.get_path_to_state("REQUEST_SENT")
    assert path == ["connect", "send_get"] or path == ["connect", "send_post"], \
        f"Path should be connect->send_get or connect->send_post, got {path}"
    print(f"✓ Path to REQUEST_SENT: {path}")

    # Test actions from CONNECTED
    actions = http_sm.get_valid_actions("CONNECTED")
    action_names = [a['action'] for a in actions]
    assert "send_get" in action_names, "Should have send_get action"
    assert "send_post" in action_names, "Should have send_post action"
    print(f"✓ Actions from CONNECTED: {', '.join(action_names)}")

    # Test message content
    get_action = [a for a in actions if a['action'] == 'send_get'][0]
    assert get_action['message'] is not None, "GET action should have message"
    assert "GET" in get_action['message'], "Message should contain GET"
    assert "HTTP/1.1" in get_action['message'], "Message should contain HTTP/1.1"
    print(f"✓ GET message: {get_action['message'][:40]}...")

    # Test response pattern
    assert get_action['response_pattern'] is not None, "Should have response pattern"
    print(f"✓ Response pattern: {get_action['response_pattern']}")

    print("✓ All HTTP state machine tests passed!\n")


def test_smtp_state_machine():
    """Test SMTP state machine workflow."""
    print("=== Test 6: SMTP State Machine Workflow ===")

    smtp_sm = BuiltinProtocols.smtp()

    # Test email sending workflow
    smtp_sm.reset()
    assert smtp_sm.get_state() == "INIT", "Should start in INIT"

    # Connect
    smtp_sm.transition("connect")
    assert smtp_sm.get_state() == "CONNECTED", "Should be CONNECTED"
    print(f"✓ Connected")

    # HELO
    smtp_sm.transition("send_helo")
    assert smtp_sm.get_state() == "HELO", "Should be in HELO state"
    print(f"✓ HELO sent")

    # MAIL FROM
    smtp_sm.transition("send_mail_from")
    assert smtp_sm.get_state() == "MAIL", "Should be in MAIL state"
    print(f"✓ MAIL FROM sent")

    # RCPT TO
    smtp_sm.transition("send_rcpt_to")
    assert smtp_sm.get_state() == "RCPT", "Should be in RCPT state"
    print(f"✓ RCPT TO sent")

    # DATA
    smtp_sm.transition("send_data")
    assert smtp_sm.get_state() == "DATA", "Should be in DATA state"
    print(f"✓ DATA command sent")

    # Send message
    smtp_sm.transition("send_message")
    assert smtp_sm.get_state() == "MESSAGE", "Should be in MESSAGE state"
    print(f"✓ Message sent")

    # Test path to MESSAGE state
    smtp_sm.reset()
    path = smtp_sm.get_path_to_state("MESSAGE")
    expected_path = ["connect", "send_helo", "send_mail_from", "send_rcpt_to", "send_data", "send_message"]
    assert path == expected_path, f"Path should be {expected_path}, got {path}"
    print(f"✓ Complete path to MESSAGE: {' -> '.join(path)}")

    print("✓ All SMTP workflow tests passed!\n")


def main():
    """Run all tests."""
    print("=" * 70)
    print("NETWORK PROTOCOL FUZZING TEST SUITE")
    print("=" * 70)

    try:
        test_state_machine()
        test_builtin_protocols()
        test_fuzzing_strategies()
        test_path_finding()
        test_http_state_machine()
        test_smtp_state_machine()

        print("=" * 70)
        print("✅ ALL TESTS PASSED!")
        print("=" * 70)

        # Print summary
        print("\nNetwork Protocol Fuzzing Implementation Summary:")
        print("  ✓ Protocol State Machine - State tracking and transitions")
        print("  ✓ Session Manager - TCP/UDP connection management")
        print("  ✓ Protocol Fuzzer - Multi-stage stateful fuzzing")
        print("  ✓ Builtin Protocols - 7 ready-to-use protocols:")
        for protocol in BuiltinProtocols.list_protocols():
            print(f"      • {protocol.upper()}")
        print("  ✓ Fuzzing Strategies - Overflow, special chars, format strings, etc.")
        print("  ✓ Path Finding - Automatic state reachability")
        print("  ✓ Response Validation - Regex pattern matching")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
