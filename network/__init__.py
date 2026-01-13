"""
Fawkes Network Protocol Fuzzing

Enhanced network protocol fuzzing with stateful, multi-stage support.

Features:
- Stateful protocol fuzzing (maintain session state)
- Multi-stage sequences (handshake -> auth -> commands)
- Protocol state machine tracking
- Network traffic capture and replay
- Built-in protocol templates (HTTP, FTP, SMTP, etc.)
"""

from .protocol_fuzzer import ProtocolFuzzer
from .state_machine import ProtocolStateMachine
from .session_manager import SessionManager
from .builtin_protocols import BuiltinProtocols

__all__ = ['ProtocolFuzzer', 'ProtocolStateMachine', 'SessionManager', 'BuiltinProtocols']
