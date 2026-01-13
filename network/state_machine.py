"""
Protocol State Machine

Models protocol states and valid transitions for stateful fuzzing.
"""

import logging
from typing import Dict, List, Optional, Set
from enum import Enum


logger = logging.getLogger("fawkes.network.state_machine")


class ProtocolStateMachine:
    """
    Models protocol state machine for stateful fuzzing.

    Example HTTP state machine:
        INIT -> CONNECTED -> REQUEST_SENT -> RESPONSE_RECEIVED -> CLOSED

    Example FTP state machine:
        INIT -> CONNECTED -> AUTHENTICATED -> COMMAND -> CLOSED
    """

    def __init__(self, name: str):
        """
        Initialize protocol state machine.

        Args:
            name: Protocol name
        """
        self.name = name
        self.states: Set[str] = set()
        self.transitions: Dict[str, List[Dict]] = {}  # state -> list of transitions
        self.initial_state: Optional[str] = None
        self.current_state: Optional[str] = None
        self.logger = logging.getLogger(f"fawkes.network.state_machine.{name}")

    def add_state(self, state: str, is_initial: bool = False):
        """
        Add state to state machine.

        Args:
            state: State name
            is_initial: Whether this is the initial state
        """
        self.states.add(state)
        if is_initial:
            self.initial_state = state
            self.current_state = state

    def add_transition(self, from_state: str, to_state: str, action: str,
                      message: str = None, response_pattern: str = None):
        """
        Add state transition.

        Args:
            from_state: Source state
            to_state: Destination state
            action: Action/message that triggers transition
            message: Message template to send
            response_pattern: Expected response pattern (regex)
        """
        if from_state not in self.states:
            self.add_state(from_state)
        if to_state not in self.states:
            self.add_state(to_state)

        if from_state not in self.transitions:
            self.transitions[from_state] = []

        transition = {
            'to_state': to_state,
            'action': action,
            'message': message,
            'response_pattern': response_pattern
        }

        self.transitions[from_state].append(transition)

    def get_valid_actions(self, state: str = None) -> List[Dict]:
        """
        Get valid actions from current or specified state.

        Args:
            state: State to query (default: current state)

        Returns:
            List of valid transitions
        """
        if state is None:
            state = self.current_state

        return self.transitions.get(state, [])

    def transition(self, action: str) -> bool:
        """
        Perform state transition.

        Args:
            action: Action to perform

        Returns:
            True if transition was valid
        """
        if not self.current_state:
            self.logger.warning("No current state set")
            return False

        # Find transition with matching action
        valid_transitions = self.get_valid_actions()

        for trans in valid_transitions:
            if trans['action'] == action:
                old_state = self.current_state
                self.current_state = trans['to_state']
                self.logger.debug(f"Transition: {old_state} --[{action}]--> {self.current_state}")
                return True

        self.logger.warning(f"Invalid transition: {action} from state {self.current_state}")
        return False

    def reset(self):
        """Reset state machine to initial state."""
        self.current_state = self.initial_state
        self.logger.debug(f"Reset to state: {self.current_state}")

    def get_state(self) -> str:
        """Get current state."""
        return self.current_state

    def is_in_state(self, state: str) -> bool:
        """Check if in specified state."""
        return self.current_state == state

    def get_path_to_state(self, target_state: str) -> Optional[List[str]]:
        """
        Get sequence of actions to reach target state.

        Uses BFS to find shortest path.

        Args:
            target_state: Target state to reach

        Returns:
            List of actions to reach target state, or None if unreachable
        """
        if target_state not in self.states:
            return None

        # BFS
        queue = [(self.initial_state, [])]
        visited = {self.initial_state}

        while queue:
            state, path = queue.pop(0)

            if state == target_state:
                return path

            # Explore transitions
            for trans in self.transitions.get(state, []):
                next_state = trans['to_state']
                if next_state not in visited:
                    visited.add(next_state)
                    queue.append((next_state, path + [trans['action']]))

        return None  # No path found

    def print_state_machine(self):
        """Print state machine diagram."""
        print("\n" + "=" * 60)
        print(f"STATE MACHINE: {self.name}")
        print("=" * 60)
        print(f"Initial state: {self.initial_state}")
        print(f"Current state: {self.current_state}")
        print(f"\nStates: {', '.join(sorted(self.states))}")
        print(f"\nTransitions:")

        for from_state, transitions in sorted(self.transitions.items()):
            print(f"\n  {from_state}:")
            for trans in transitions:
                msg = f"[{trans['action']}]"
                if trans['message']:
                    msg += f" ({trans['message'][:30]}...)"
                print(f"    -> {trans['to_state']} {msg}")

        print("=" * 60)


# Convenience function
def create_state_machine(name: str) -> ProtocolStateMachine:
    """
    Quick function to create state machine.

    Args:
        name: Protocol name

    Returns:
        ProtocolStateMachine instance

    Example:
        >>> sm = create_state_machine("HTTP")
        >>> sm.add_state("INIT", is_initial=True)
        >>> sm.add_state("CONNECTED")
        >>> sm.add_transition("INIT", "CONNECTED", "connect")
    """
    return ProtocolStateMachine(name)


# Testing
if __name__ == "__main__":
    # Create HTTP state machine
    http_sm = ProtocolStateMachine("HTTP")

    # Add states
    http_sm.add_state("INIT", is_initial=True)
    http_sm.add_state("CONNECTED")
    http_sm.add_state("REQUEST_SENT")
    http_sm.add_state("RESPONSE_RECEIVED")
    http_sm.add_state("CLOSED")

    # Add transitions
    http_sm.add_transition("INIT", "CONNECTED", "connect", "")
    http_sm.add_transition("CONNECTED", "REQUEST_SENT", "send_request",
                          "GET / HTTP/1.1\\r\\nHost: example.com\\r\\n\\r\\n")
    http_sm.add_transition("REQUEST_SENT", "RESPONSE_RECEIVED", "recv_response")
    http_sm.add_transition("RESPONSE_RECEIVED", "CLOSED", "close")
    http_sm.add_transition("RESPONSE_RECEIVED", "REQUEST_SENT", "send_request")

    # Print state machine
    http_sm.print_state_machine()

    # Test transitions
    print("\nTesting transitions:")
    print(f"Current state: {http_sm.get_state()}")

    http_sm.transition("connect")
    print(f"After connect: {http_sm.get_state()}")

    http_sm.transition("send_request")
    print(f"After request: {http_sm.get_state()}")

    # Get path to state
    path = http_sm.get_path_to_state("RESPONSE_RECEIVED")
    print(f"\nPath to RESPONSE_RECEIVED: {path}")
