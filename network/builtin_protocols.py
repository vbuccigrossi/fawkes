"""
Builtin Protocol Definitions

Pre-configured state machines for common network protocols.
"""

from .state_machine import ProtocolStateMachine


class BuiltinProtocols:
    """
    Collection of pre-defined protocol state machines.

    Supported protocols:
    - HTTP (GET, POST)
    - FTP (login, commands)
    - SMTP (email delivery)
    - POP3 (email retrieval)
    - IMAP (email access)
    - DNS (queries)
    - SSH (authentication)
    """

    @staticmethod
    def http() -> ProtocolStateMachine:
        """
        HTTP protocol state machine.

        States:
            INIT -> CONNECTED -> REQUEST_SENT -> RESPONSE_RECEIVED -> CLOSED

        Returns:
            ProtocolStateMachine for HTTP

        Example:
            >>> http_sm = BuiltinProtocols.http()
            >>> fuzzer = ProtocolFuzzer("example.com", 80, http_sm)
        """
        sm = ProtocolStateMachine("HTTP")

        # States
        sm.add_state("INIT", is_initial=True)
        sm.add_state("CONNECTED")
        sm.add_state("REQUEST_SENT")
        sm.add_state("RESPONSE_RECEIVED")
        sm.add_state("CLOSED")

        # Transitions
        sm.add_transition("INIT", "CONNECTED", "connect")

        # GET request
        sm.add_transition(
            "CONNECTED", "REQUEST_SENT", "send_get",
            message="GET / HTTP/1.1\r\nHost: target\r\nUser-Agent: Fawkes/1.0\r\nConnection: keep-alive\r\n\r\n",
            response_pattern=r"HTTP/1\.[01] \d{3}"
        )

        # POST request
        sm.add_transition(
            "CONNECTED", "REQUEST_SENT", "send_post",
            message="POST / HTTP/1.1\r\nHost: target\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 13\r\n\r\nkey=value&x=1",
            response_pattern=r"HTTP/1\.[01] \d{3}"
        )

        # Receive response
        sm.add_transition(
            "REQUEST_SENT", "RESPONSE_RECEIVED", "recv_response"
        )

        # Keep-alive: send another request
        sm.add_transition(
            "RESPONSE_RECEIVED", "REQUEST_SENT", "send_get"
        )

        # Close connection
        sm.add_transition(
            "RESPONSE_RECEIVED", "CLOSED", "close"
        )
        sm.add_transition(
            "CONNECTED", "CLOSED", "close"
        )

        return sm

    @staticmethod
    def ftp() -> ProtocolStateMachine:
        """
        FTP protocol state machine.

        States:
            INIT -> CONNECTED -> AUTHENTICATED -> COMMAND -> DATA_TRANSFER -> CLOSED

        Returns:
            ProtocolStateMachine for FTP
        """
        sm = ProtocolStateMachine("FTP")

        # States
        sm.add_state("INIT", is_initial=True)
        sm.add_state("CONNECTED")
        sm.add_state("USER_SENT")
        sm.add_state("AUTHENTICATED")
        sm.add_state("COMMAND")
        sm.add_state("DATA_TRANSFER")
        sm.add_state("CLOSED")

        # Transitions
        sm.add_transition(
            "INIT", "CONNECTED", "connect",
            response_pattern=r"220"
        )

        # Authentication
        sm.add_transition(
            "CONNECTED", "USER_SENT", "send_user",
            message="USER anonymous\r\n",
            response_pattern=r"331"
        )

        sm.add_transition(
            "USER_SENT", "AUTHENTICATED", "send_pass",
            message="PASS guest@\r\n",
            response_pattern=r"230"
        )

        # Commands
        sm.add_transition(
            "AUTHENTICATED", "COMMAND", "send_pwd",
            message="PWD\r\n",
            response_pattern=r"257"
        )

        sm.add_transition(
            "AUTHENTICATED", "COMMAND", "send_list",
            message="LIST\r\n",
            response_pattern=r"150|226"
        )

        sm.add_transition(
            "AUTHENTICATED", "COMMAND", "send_cwd",
            message="CWD /pub\r\n",
            response_pattern=r"250"
        )

        sm.add_transition(
            "COMMAND", "COMMAND", "send_pwd"
        )

        # Data transfer
        sm.add_transition(
            "COMMAND", "DATA_TRANSFER", "send_retr",
            message="RETR file.txt\r\n",
            response_pattern=r"150"
        )

        sm.add_transition(
            "DATA_TRANSFER", "COMMAND", "data_complete",
            response_pattern=r"226"
        )

        # Quit
        sm.add_transition(
            "AUTHENTICATED", "CLOSED", "send_quit",
            message="QUIT\r\n",
            response_pattern=r"221"
        )
        sm.add_transition(
            "COMMAND", "CLOSED", "send_quit"
        )

        return sm

    @staticmethod
    def smtp() -> ProtocolStateMachine:
        """
        SMTP protocol state machine.

        States:
            INIT -> CONNECTED -> HELO -> MAIL -> RCPT -> DATA -> MESSAGE -> CLOSED

        Returns:
            ProtocolStateMachine for SMTP
        """
        sm = ProtocolStateMachine("SMTP")

        # States
        sm.add_state("INIT", is_initial=True)
        sm.add_state("CONNECTED")
        sm.add_state("HELO")
        sm.add_state("MAIL")
        sm.add_state("RCPT")
        sm.add_state("DATA")
        sm.add_state("MESSAGE")
        sm.add_state("CLOSED")

        # Transitions
        sm.add_transition(
            "INIT", "CONNECTED", "connect",
            response_pattern=r"220"
        )

        sm.add_transition(
            "CONNECTED", "HELO", "send_helo",
            message="HELO client.local\r\n",
            response_pattern=r"250"
        )

        sm.add_transition(
            "HELO", "MAIL", "send_mail_from",
            message="MAIL FROM:<sender@example.com>\r\n",
            response_pattern=r"250"
        )

        sm.add_transition(
            "MAIL", "RCPT", "send_rcpt_to",
            message="RCPT TO:<recipient@example.com>\r\n",
            response_pattern=r"250"
        )

        # Multiple recipients
        sm.add_transition(
            "RCPT", "RCPT", "send_rcpt_to"
        )

        sm.add_transition(
            "RCPT", "DATA", "send_data",
            message="DATA\r\n",
            response_pattern=r"354"
        )

        sm.add_transition(
            "DATA", "MESSAGE", "send_message",
            message="Subject: Test\r\n\r\nThis is a test message.\r\n.\r\n",
            response_pattern=r"250"
        )

        # Send another email
        sm.add_transition(
            "MESSAGE", "MAIL", "send_mail_from"
        )

        sm.add_transition(
            "MESSAGE", "CLOSED", "send_quit",
            message="QUIT\r\n",
            response_pattern=r"221"
        )

        return sm

    @staticmethod
    def pop3() -> ProtocolStateMachine:
        """
        POP3 protocol state machine.

        States:
            INIT -> CONNECTED -> AUTHENTICATED -> TRANSACTION -> CLOSED

        Returns:
            ProtocolStateMachine for POP3
        """
        sm = ProtocolStateMachine("POP3")

        # States
        sm.add_state("INIT", is_initial=True)
        sm.add_state("CONNECTED")
        sm.add_state("USER_SENT")
        sm.add_state("AUTHENTICATED")
        sm.add_state("TRANSACTION")
        sm.add_state("CLOSED")

        # Transitions
        sm.add_transition(
            "INIT", "CONNECTED", "connect",
            response_pattern=r"\+OK"
        )

        sm.add_transition(
            "CONNECTED", "USER_SENT", "send_user",
            message="USER testuser\r\n",
            response_pattern=r"\+OK"
        )

        sm.add_transition(
            "USER_SENT", "AUTHENTICATED", "send_pass",
            message="PASS testpass\r\n",
            response_pattern=r"\+OK"
        )

        # Transaction commands
        sm.add_transition(
            "AUTHENTICATED", "TRANSACTION", "send_stat",
            message="STAT\r\n",
            response_pattern=r"\+OK"
        )

        sm.add_transition(
            "AUTHENTICATED", "TRANSACTION", "send_list",
            message="LIST\r\n",
            response_pattern=r"\+OK"
        )

        sm.add_transition(
            "TRANSACTION", "TRANSACTION", "send_retr",
            message="RETR 1\r\n",
            response_pattern=r"\+OK"
        )

        sm.add_transition(
            "TRANSACTION", "TRANSACTION", "send_dele",
            message="DELE 1\r\n",
            response_pattern=r"\+OK"
        )

        sm.add_transition(
            "TRANSACTION", "CLOSED", "send_quit",
            message="QUIT\r\n",
            response_pattern=r"\+OK"
        )

        return sm

    @staticmethod
    def imap() -> ProtocolStateMachine:
        """
        IMAP protocol state machine.

        States:
            INIT -> CONNECTED -> AUTHENTICATED -> SELECTED -> CLOSED

        Returns:
            ProtocolStateMachine for IMAP
        """
        sm = ProtocolStateMachine("IMAP")

        # States
        sm.add_state("INIT", is_initial=True)
        sm.add_state("CONNECTED")
        sm.add_state("AUTHENTICATED")
        sm.add_state("SELECTED")
        sm.add_state("CLOSED")

        # Transitions
        sm.add_transition(
            "INIT", "CONNECTED", "connect",
            response_pattern=r"\* OK"
        )

        sm.add_transition(
            "CONNECTED", "AUTHENTICATED", "send_login",
            message="A001 LOGIN testuser testpass\r\n",
            response_pattern=r"A001 OK"
        )

        sm.add_transition(
            "AUTHENTICATED", "SELECTED", "send_select",
            message="A002 SELECT INBOX\r\n",
            response_pattern=r"A002 OK"
        )

        sm.add_transition(
            "SELECTED", "SELECTED", "send_fetch",
            message="A003 FETCH 1 BODY[]\r\n",
            response_pattern=r"A003 OK"
        )

        sm.add_transition(
            "SELECTED", "SELECTED", "send_search",
            message="A004 SEARCH ALL\r\n",
            response_pattern=r"A004 OK"
        )

        sm.add_transition(
            "AUTHENTICATED", "AUTHENTICATED", "send_list",
            message="A005 LIST \"\" \"*\"\r\n",
            response_pattern=r"A005 OK"
        )

        sm.add_transition(
            "AUTHENTICATED", "CLOSED", "send_logout",
            message="A006 LOGOUT\r\n",
            response_pattern=r"A006 OK"
        )
        sm.add_transition(
            "SELECTED", "CLOSED", "send_logout"
        )

        return sm

    @staticmethod
    def ssh() -> ProtocolStateMachine:
        """
        SSH protocol state machine (simplified).

        States:
            INIT -> CONNECTED -> VERSION_EXCHANGE -> KEY_EXCHANGE -> AUTHENTICATED -> CLOSED

        Returns:
            ProtocolStateMachine for SSH

        Note:
            This is a simplified state machine. Real SSH uses complex cryptography.
        """
        sm = ProtocolStateMachine("SSH")

        # States
        sm.add_state("INIT", is_initial=True)
        sm.add_state("CONNECTED")
        sm.add_state("VERSION_EXCHANGE")
        sm.add_state("KEY_EXCHANGE")
        sm.add_state("AUTHENTICATED")
        sm.add_state("CLOSED")

        # Transitions
        sm.add_transition(
            "INIT", "CONNECTED", "connect"
        )

        sm.add_transition(
            "CONNECTED", "VERSION_EXCHANGE", "send_version",
            message="SSH-2.0-Fawkes_1.0\r\n",
            response_pattern=r"SSH-2\.0"
        )

        # Note: Real SSH key exchange is complex binary protocol
        sm.add_transition(
            "VERSION_EXCHANGE", "KEY_EXCHANGE", "send_kex_init"
        )

        sm.add_transition(
            "KEY_EXCHANGE", "AUTHENTICATED", "send_auth"
        )

        sm.add_transition(
            "AUTHENTICATED", "CLOSED", "disconnect"
        )

        return sm

    @staticmethod
    def telnet() -> ProtocolStateMachine:
        """
        Telnet protocol state machine.

        States:
            INIT -> CONNECTED -> NEGOTIATION -> AUTHENTICATED -> COMMAND -> CLOSED

        Returns:
            ProtocolStateMachine for Telnet
        """
        sm = ProtocolStateMachine("TELNET")

        # States
        sm.add_state("INIT", is_initial=True)
        sm.add_state("CONNECTED")
        sm.add_state("NEGOTIATION")
        sm.add_state("LOGIN_PROMPT")
        sm.add_state("PASSWORD_PROMPT")
        sm.add_state("AUTHENTICATED")
        sm.add_state("COMMAND")
        sm.add_state("CLOSED")

        # Transitions
        sm.add_transition(
            "INIT", "CONNECTED", "connect"
        )

        sm.add_transition(
            "CONNECTED", "NEGOTIATION", "negotiate",
            response_pattern=r"login:|Username:"
        )

        sm.add_transition(
            "NEGOTIATION", "LOGIN_PROMPT", "wait_login"
        )

        sm.add_transition(
            "LOGIN_PROMPT", "PASSWORD_PROMPT", "send_username",
            message="testuser\r\n",
            response_pattern=r"Password:"
        )

        sm.add_transition(
            "PASSWORD_PROMPT", "AUTHENTICATED", "send_password",
            message="testpass\r\n",
            response_pattern=r"[$#>]"
        )

        sm.add_transition(
            "AUTHENTICATED", "COMMAND", "send_command",
            message="ls -la\r\n",
            response_pattern=r"[$#>]"
        )

        sm.add_transition(
            "COMMAND", "COMMAND", "send_command"
        )

        sm.add_transition(
            "COMMAND", "CLOSED", "send_exit",
            message="exit\r\n"
        )

        return sm

    @staticmethod
    def get_all_protocols():
        """
        Get all available protocol state machines.

        Returns:
            Dict mapping protocol names to state machines
        """
        return {
            'http': BuiltinProtocols.http(),
            'ftp': BuiltinProtocols.ftp(),
            'smtp': BuiltinProtocols.smtp(),
            'pop3': BuiltinProtocols.pop3(),
            'imap': BuiltinProtocols.imap(),
            'ssh': BuiltinProtocols.ssh(),
            'telnet': BuiltinProtocols.telnet()
        }

    @staticmethod
    def list_protocols():
        """
        List all available protocol names.

        Returns:
            List of protocol names
        """
        return ['http', 'ftp', 'smtp', 'pop3', 'imap', 'ssh', 'telnet']


# Testing
if __name__ == "__main__":
    print("Available Protocol State Machines:")
    print("=" * 60)

    for name in BuiltinProtocols.list_protocols():
        print(f"\n{name.upper()}:")
        protocols = BuiltinProtocols.get_all_protocols()
        sm = protocols[name]
        sm.print_state_machine()
