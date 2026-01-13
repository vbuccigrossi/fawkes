"""
Protocol Fuzzer

Stateful network protocol fuzzing engine.
"""

import time
import logging
import random
from typing import List, Optional, Dict

from .state_machine import ProtocolStateMachine
from .session_manager import SessionManager


logger = logging.getLogger("fawkes.network.protocol_fuzzer")


class ProtocolFuzzer:
    """
    Stateful network protocol fuzzer.

    Features:
    - Multi-stage fuzzing sequences
    - State-aware fuzzing
    - Response validation
    - Crash detection
    """

    def __init__(self, host: str, port: int, state_machine: ProtocolStateMachine,
                 timeout: int = 5, max_retries: int = 3):
        """
        Initialize protocol fuzzer.

        Args:
            host: Target host
            port: Target port
            state_machine: Protocol state machine
            timeout: Connection timeout
            max_retries: Maximum connection retries
        """
        self.host = host
        self.port = port
        self.state_machine = state_machine
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(f"fawkes.network.protocol_fuzzer")

        self.session: Optional[SessionManager] = None
        self.iterations = 0
        self.crashes_found = 0

    def start_session(self) -> bool:
        """
        Start fuzzing session.

        Returns:
            True if session started successfully
        """
        self.session = SessionManager(self.host, self.port, "TCP", self.timeout)

        for attempt in range(self.max_retries):
            if self.session.connect():
                self.state_machine.reset()
                self.logger.info("Fuzzing session started")
                return True

            self.logger.warning(f"Connection attempt {attempt + 1} failed")
            time.sleep(1)

        self.logger.error("Failed to start session")
        return False

    def execute_action(self, action: str, fuzz: bool = False) -> bool:
        """
        Execute protocol action.

        Args:
            action: Action to execute
            fuzz: Whether to fuzz the message

        Returns:
            True if action executed successfully
        """
        if not self.session or not self.session.is_connected():
            self.logger.error("No active session")
            return False

        # Get transition for this action
        valid_actions = self.state_machine.get_valid_actions()
        transition = None

        for trans in valid_actions:
            if trans['action'] == action:
                transition = trans
                break

        if not transition:
            self.logger.warning(f"Invalid action: {action}")
            return False

        # Get message to send
        message = transition.get('message', '')

        if not message:
            # Action doesn't send a message (e.g., close, connect)
            return self.state_machine.transition(action)

        # Fuzz message if requested
        if fuzz:
            message = self._fuzz_message(message)

        # Send message
        message_bytes = message.encode('utf-8')
        response = self.session.send_and_receive(message_bytes)

        if response is None:
            self.logger.warning("No response received")
            return False

        # Validate response if pattern specified
        response_pattern = transition.get('response_pattern')
        if response_pattern:
            import re
            if not re.search(response_pattern, response.decode('utf-8', errors='ignore')):
                self.logger.warning(f"Response doesn't match pattern: {response_pattern}")
                # Possible crash or unexpected behavior
                self.crashes_found += 1

        # Transition state
        return self.state_machine.transition(action)

    def reach_state(self, target_state: str) -> bool:
        """
        Reach specific protocol state.

        Args:
            target_state: Target state to reach

        Returns:
            True if state reached successfully
        """
        # Get path to target state
        path = self.state_machine.get_path_to_state(target_state)

        if not path:
            self.logger.error(f"No path to state: {target_state}")
            return False

        # Execute action sequence
        for action in path:
            if not self.execute_action(action, fuzz=False):
                self.logger.error(f"Failed to execute action: {action}")
                return False

        self.logger.info(f"Reached state: {target_state}")
        return True

    def fuzz_state(self, state: str, iterations: int = 10) -> int:
        """
        Fuzz all actions from a specific state.

        Args:
            state: State to fuzz from
            iterations: Number of fuzzing iterations per action

        Returns:
            Number of potential crashes found
        """
        crashes = 0

        # Reach the target state first
        if not self.reach_state(state):
            return 0

        # Get valid actions from this state
        valid_actions = self.state_machine.get_valid_actions(state)

        for action_trans in valid_actions:
            action = action_trans['action']

            for i in range(iterations):
                # Reset to target state
                self.session.reset()
                self.state_machine.reset()

                if not self.reach_state(state):
                    continue

                # Execute action with fuzzing
                self.logger.debug(f"Fuzzing action: {action} (iteration {i+1}/{iterations})")

                try:
                    if not self.execute_action(action, fuzz=True):
                        crashes += 1
                        self.logger.info(f"Potential crash detected: {action}")

                except Exception as e:
                    crashes += 1
                    self.logger.error(f"Exception during fuzzing: {e}")

                self.iterations += 1

        return crashes

    def fuzz_all_states(self, iterations_per_action: int = 10) -> Dict:
        """
        Fuzz all states in state machine.

        Args:
            iterations_per_action: Fuzzing iterations per action

        Returns:
            Dict with fuzzing statistics
        """
        total_crashes = 0
        states_fuzzed = 0

        for state in self.state_machine.states:
            self.logger.info(f"Fuzzing state: {state}")
            crashes = self.fuzz_state(state, iterations_per_action)
            total_crashes += crashes
            states_fuzzed += 1

        return {
            'states_fuzzed': states_fuzzed,
            'total_iterations': self.iterations,
            'crashes_found': total_crashes
        }

    def _fuzz_message(self, message: str) -> str:
        """
        Fuzz a message string.

        Args:
            message: Original message

        Returns:
            Fuzzed message
        """
        # Simple fuzzing strategies
        strategies = [
            self._fuzz_overflow,
            self._fuzz_special_chars,
            self._fuzz_format_strings,
            self._fuzz_truncate,
            self._fuzz_repeat
        ]

        strategy = random.choice(strategies)
        return strategy(message)

    def _fuzz_overflow(self, message: str) -> str:
        """Add long strings to trigger overflows."""
        overflow = "A" * random.randint(100, 10000)
        parts = message.split(' ')
        if parts:
            idx = random.randint(0, len(parts) - 1)
            parts[idx] += overflow
        return ' '.join(parts)

    def _fuzz_special_chars(self, message: str) -> str:
        """Insert special characters."""
        special_chars = ['\x00', '\n', '\r', '\t', '%', '\\', '\"', '\'', '<', '>', '&']
        char = random.choice(special_chars)
        pos = random.randint(0, len(message))
        return message[:pos] + char * random.randint(1, 10) + message[pos:]

    def _fuzz_format_strings(self, message: str) -> str:
        """Insert format string specifiers."""
        format_strings = ['%s', '%x', '%n', '%p', '%d']
        fmt = random.choice(format_strings)
        return message + fmt * random.randint(1, 20)

    def _fuzz_truncate(self, message: str) -> str:
        """Truncate message."""
        if len(message) > 2:
            pos = random.randint(1, len(message) - 1)
            return message[:pos]
        return message

    def _fuzz_repeat(self, message: str) -> str:
        """Repeat parts of message."""
        if message:
            parts = message.split(' ')
            if parts:
                repeated = random.choice(parts) * random.randint(2, 100)
                return message + ' ' + repeated
        return message

    def close(self):
        """Close fuzzing session."""
        if self.session:
            self.session.close()


# Testing
if __name__ == "__main__":
    from state_machine import ProtocolStateMachine

    # Create simple HTTP state machine
    http_sm = ProtocolStateMachine("HTTP")
    http_sm.add_state("INIT", is_initial=True)
    http_sm.add_state("CONNECTED")
    http_sm.add_state("REQUEST_SENT")

    http_sm.add_transition("INIT", "CONNECTED", "connect")
    http_sm.add_transition("CONNECTED", "REQUEST_SENT", "send_request",
                          message="GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
                          response_pattern=r"HTTP/1\.[01] \d{3}")

    # Create fuzzer
    fuzzer = ProtocolFuzzer("example.com", 80, http_sm)

    print("Starting fuzzing session...")
    if fuzzer.start_session():
        # Reach REQUEST_SENT state
        if fuzzer.reach_state("REQUEST_SENT"):
            print("Successfully reached REQUEST_SENT state")

        # Fuzz the CONNECTED state
        crashes = fuzzer.fuzz_state("CONNECTED", iterations=5)
        print(f"Found {crashes} potential crashes")

        fuzzer.close()
    else:
        print("Failed to start session")
