"""
Grammar Parser

Parses BNF/EBNF grammar specifications into internal representation.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple


logger = logging.getLogger("fawkes.grammar.parser")


class GrammarParser:
    """
    Parses BNF/EBNF grammar specifications.

    Supported syntax:
    - BNF: <rule> ::= <production> | <alternative>
    - EBNF extensions: {repetition}, [optional], (grouping)
    - Terminal strings: "literal" or 'literal'
    - Comments: # comment

    Example grammar:
        <json> ::= <object> | <array>
        <object> ::= "{" [<members>] "}"
        <members> ::= <pair> | <pair> "," <members>
        <pair> ::= <string> ":" <value>
        <array> ::= "[" [<elements>] "]"
        <elements> ::= <value> | <value> "," <elements>
        <value> ::= <string> | <number> | <object> | <array> | "true" | "false" | "null"
        <string> ::= '"' {<char>} '"'
        <number> ::= <digit> {<digit>}
        <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
        <char> ::= "a" | "b" | ... | "z"  # simplified
    """

    def __init__(self):
        self.logger = logging.getLogger("fawkes.grammar.parser")
        self.rules: Dict[str, List] = {}

    def parse(self, grammar_text: str) -> Dict[str, List]:
        """
        Parse grammar text into internal representation.

        Args:
            grammar_text: Grammar in BNF/EBNF format

        Returns:
            Dict mapping rule names to productions
        """
        self.rules = {}

        for line in grammar_text.split('\n'):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Parse rule
            if '::=' in line:
                self._parse_rule(line)

        self.logger.info(f"Parsed grammar with {len(self.rules)} rules")
        return self.rules

    def _parse_rule(self, line: str):
        """Parse a single grammar rule."""
        # Split on ::=
        if '::=' not in line:
            return

        parts = line.split('::=', 1)
        if len(parts) != 2:
            self.logger.warning(f"Invalid rule: {line}")
            return

        rule_name = parts[0].strip()
        productions_text = parts[1].strip()

        # Extract rule name (remove < >)
        rule_name = rule_name.strip('<>').strip()

        # Parse productions (separated by |)
        productions = []
        for prod_text in productions_text.split('|'):
            prod_text = prod_text.strip()
            if prod_text:
                production = self._parse_production(prod_text)
                productions.append(production)

        self.rules[rule_name] = productions

    def _parse_production(self, prod_text: str) -> List:
        """
        Parse a single production into a list of elements.

        Elements can be:
        - Terminal: {'type': 'terminal', 'value': 'literal'}
        - NonTerminal: {'type': 'nonterminal', 'name': 'rule_name'}
        - Optional: {'type': 'optional', 'content': [...]}
        - Repetition: {'type': 'repetition', 'content': [...]}
        - Group: {'type': 'group', 'content': [...]}
        """
        elements = []
        i = 0

        while i < len(prod_text):
            char = prod_text[i]

            # Terminal string (quoted)
            if char in ('"', "'"):
                terminal, end_pos = self._parse_terminal(prod_text, i)
                elements.append(terminal)
                i = end_pos
                continue

            # Optional [...]
            elif char == '[':
                optional, end_pos = self._parse_optional(prod_text, i)
                elements.append(optional)
                i = end_pos
                continue

            # Repetition {...}
            elif char == '{':
                repetition, end_pos = self._parse_repetition(prod_text, i)
                elements.append(repetition)
                i = end_pos
                continue

            # Group (...)
            elif char == '(':
                group, end_pos = self._parse_group(prod_text, i)
                elements.append(group)
                i = end_pos
                continue

            # NonTerminal <rule_name>
            elif char == '<':
                nonterminal, end_pos = self._parse_nonterminal(prod_text, i)
                elements.append(nonterminal)
                i = end_pos
                continue

            # Skip whitespace
            elif char.isspace():
                i += 1
                continue

            else:
                i += 1

        return elements

    def _parse_terminal(self, text: str, start: int) -> Tuple[Dict, int]:
        """Parse terminal string."""
        quote_char = text[start]
        end = text.find(quote_char, start + 1)

        if end == -1:
            self.logger.warning(f"Unclosed quote at position {start}")
            end = len(text)

        value = text[start + 1:end]
        return {'type': 'terminal', 'value': value}, end + 1

    def _parse_nonterminal(self, text: str, start: int) -> Tuple[Dict, int]:
        """Parse non-terminal <rule_name>."""
        end = text.find('>', start)

        if end == -1:
            self.logger.warning(f"Unclosed non-terminal at position {start}")
            end = len(text)

        name = text[start + 1:end].strip()
        return {'type': 'nonterminal', 'name': name}, end + 1

    def _parse_optional(self, text: str, start: int) -> Tuple[Dict, int]:
        """Parse optional [...]."""
        end = self._find_matching_bracket(text, start, '[', ']')
        content_text = text[start + 1:end]
        content = self._parse_production(content_text)
        return {'type': 'optional', 'content': content}, end + 1

    def _parse_repetition(self, text: str, start: int) -> Tuple[Dict, int]:
        """Parse repetition {...}."""
        end = self._find_matching_bracket(text, start, '{', '}')
        content_text = text[start + 1:end]
        content = self._parse_production(content_text)
        return {'type': 'repetition', 'content': content}, end + 1

    def _parse_group(self, text: str, start: int) -> Tuple[Dict, int]:
        """Parse group (...)."""
        end = self._find_matching_bracket(text, start, '(', ')')
        content_text = text[start + 1:end]
        content = self._parse_production(content_text)
        return {'type': 'group', 'content': content}, end + 1

    def _find_matching_bracket(self, text: str, start: int, open_char: str, close_char: str) -> int:
        """Find matching closing bracket."""
        count = 1
        i = start + 1

        while i < len(text) and count > 0:
            if text[i] == open_char:
                count += 1
            elif text[i] == close_char:
                count -= 1
            i += 1

        return i - 1 if count == 0 else len(text)

    def get_rule(self, rule_name: str) -> Optional[List]:
        """Get productions for a rule."""
        return self.rules.get(rule_name)

    def get_all_rules(self) -> Dict[str, List]:
        """Get all rules."""
        return self.rules

    def validate(self) -> bool:
        """
        Validate grammar (check for undefined non-terminals).

        Returns:
            True if grammar is valid
        """
        valid = True

        for rule_name, productions in self.rules.items():
            for production in productions:
                if not self._validate_production(production):
                    valid = False

        return valid

    def _validate_production(self, production: List) -> bool:
        """Validate production elements."""
        valid = True

        for element in production:
            if element['type'] == 'nonterminal':
                # Check if rule exists
                if element['name'] not in self.rules:
                    self.logger.warning(f"Undefined non-terminal: <{element['name']}>")
                    valid = False

            elif element['type'] in ('optional', 'repetition', 'group'):
                # Recursively validate content
                if not self._validate_production(element['content']):
                    valid = False

        return valid

    def print_grammar(self):
        """Print parsed grammar in human-readable format."""
        print("\n" + "=" * 60)
        print("PARSED GRAMMAR")
        print("=" * 60)

        for rule_name, productions in self.rules.items():
            print(f"\n<{rule_name}> ::=")
            for i, production in enumerate(productions):
                if i > 0:
                    print("  |", end=" ")
                else:
                    print("   ", end=" ")
                self._print_production(production)
                print()

        print("=" * 60)

    def _print_production(self, production: List):
        """Print a single production."""
        for element in production:
            if element['type'] == 'terminal':
                print(f'"{element["value"]}"', end=" ")
            elif element['type'] == 'nonterminal':
                print(f"<{element['name']}>", end=" ")
            elif element['type'] == 'optional':
                print("[", end="")
                self._print_production(element['content'])
                print("]", end=" ")
            elif element['type'] == 'repetition':
                print("{", end="")
                self._print_production(element['content'])
                print("}", end=" ")
            elif element['type'] == 'group':
                print("(", end="")
                self._print_production(element['content'])
                print(")", end=" ")


# Convenience function
def parse_grammar(grammar_text: str) -> Dict[str, List]:
    """
    Quick function to parse grammar.

    Args:
        grammar_text: Grammar in BNF/EBNF format

    Returns:
        Parsed grammar rules

    Example:
        >>> grammar = '''
        ... <expr> ::= <term> | <expr> "+" <term>
        ... <term> ::= <number> | "(" <expr> ")"
        ... <number> ::= "0" | "1" | "2"
        ... '''
        >>> rules = parse_grammar(grammar)
    """
    parser = GrammarParser()
    return parser.parse(grammar_text)


# Testing
if __name__ == "__main__":
    # Test grammar parser
    test_grammar = """
    # Simple arithmetic grammar
    <expr> ::= <term> | <expr> "+" <term> | <expr> "-" <term>
    <term> ::= <factor> | <term> "*" <factor> | <term> "/" <factor>
    <factor> ::= <number> | "(" <expr> ")"
    <number> ::= <digit> {<digit>}
    <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
    """

    parser = GrammarParser()
    rules = parser.parse(test_grammar)

    print(f"Parsed {len(rules)} rules:")
    for rule_name in rules:
        print(f"  - <{rule_name}>")

    parser.print_grammar()

    # Validate
    if parser.validate():
        print("\n✓ Grammar is valid")
    else:
        print("\n✗ Grammar has errors")
