"""
Grammar Generator

Generates strings from grammar specifications.
"""

import random
import logging
from typing import Dict, List, Optional


logger = logging.getLogger("fawkes.grammar.generator")


class GrammarGenerator:
    """
    Generates strings from parsed grammar.

    Features:
    - Recursive generation from start symbol
    - Configurable recursion depth
    - Random production selection
    - Size constraints
    """

    def __init__(self, grammar: Dict[str, List], max_depth: int = 10, max_length: int = 1000):
        """
        Initialize grammar generator.

        Args:
            grammar: Parsed grammar rules
            max_depth: Maximum recursion depth
            max_length: Maximum generated string length
        """
        self.grammar = grammar
        self.max_depth = max_depth
        self.max_length = max_length
        self.logger = logging.getLogger("fawkes.grammar.generator")

    def generate(self, start_symbol: str = None, seed: int = None) -> str:
        """
        Generate string from grammar.

        Args:
            start_symbol: Starting rule (default: first rule)
            seed: Random seed for reproducibility

        Returns:
            Generated string
        """
        if seed is not None:
            random.seed(seed)

        # Use first rule if no start symbol specified
        if start_symbol is None:
            if not self.grammar:
                return ""
            start_symbol = list(self.grammar.keys())[0]

        # Generate from start symbol
        result = self._generate_symbol(start_symbol, depth=0)

        # Truncate if too long
        if len(result) > self.max_length:
            result = result[:self.max_length]

        return result

    def _generate_symbol(self, symbol: str, depth: int) -> str:
        """
        Generate string from a non-terminal symbol.

        Args:
            symbol: Non-terminal symbol name
            depth: Current recursion depth

        Returns:
            Generated string
        """
        # Check depth limit
        if depth >= self.max_depth:
            # Try to find a non-recursive production
            return self._generate_terminal_production(symbol)

        # Get productions for this symbol
        productions = self.grammar.get(symbol)
        if not productions:
            self.logger.warning(f"No productions for symbol: <{symbol}>")
            return ""

        # Select random production
        production = random.choice(productions)

        # Generate from production
        return self._generate_production(production, depth)

    def _generate_production(self, production: List, depth: int) -> str:
        """Generate string from a production."""
        result = []

        for element in production:
            if element['type'] == 'terminal':
                # Terminal: just append the literal
                result.append(element['value'])

            elif element['type'] == 'nonterminal':
                # Non-terminal: recursively generate
                generated = self._generate_symbol(element['name'], depth + 1)
                result.append(generated)

            elif element['type'] == 'optional':
                # Optional: 50% chance to include
                if random.random() < 0.5:
                    generated = self._generate_production(element['content'], depth)
                    result.append(generated)

            elif element['type'] == 'repetition':
                # Repetition: repeat 0-5 times
                repeat_count = random.randint(0, min(5, self.max_depth - depth))
                for _ in range(repeat_count):
                    generated = self._generate_production(element['content'], depth)
                    result.append(generated)

            elif element['type'] == 'group':
                # Group: just generate the content
                generated = self._generate_production(element['content'], depth)
                result.append(generated)

        return ''.join(result)

    def _generate_terminal_production(self, symbol: str) -> str:
        """
        Generate from a production with only terminals (for depth limit).

        Args:
            symbol: Symbol to generate from

        Returns:
            Generated string
        """
        productions = self.grammar.get(symbol, [])

        # Try to find production with only terminals
        for production in productions:
            if self._is_terminal_production(production):
                return self._generate_production(production, self.max_depth)

        # Fallback: use first production
        if productions:
            return self._generate_production(productions[0], self.max_depth)

        return ""

    def _is_terminal_production(self, production: List) -> bool:
        """Check if production contains only terminals."""
        for element in production:
            if element['type'] == 'nonterminal':
                return False
            elif element['type'] in ('optional', 'repetition', 'group'):
                if not self._is_terminal_production(element['content']):
                    return False
        return True

    def generate_batch(self, count: int, start_symbol: str = None) -> List[str]:
        """
        Generate multiple strings.

        Args:
            count: Number of strings to generate
            start_symbol: Starting rule

        Returns:
            List of generated strings
        """
        return [self.generate(start_symbol) for _ in range(count)]

    def get_statistics(self, samples: int = 100) -> Dict:
        """
        Get statistics about generated strings.

        Args:
            samples: Number of samples to analyze

        Returns:
            Dict with statistics
        """
        generated = self.generate_batch(samples)

        lengths = [len(s) for s in generated]
        unique = len(set(generated))

        return {
            'samples': samples,
            'avg_length': sum(lengths) / len(lengths) if lengths else 0,
            'min_length': min(lengths) if lengths else 0,
            'max_length': max(lengths) if lengths else 0,
            'unique_count': unique,
            'uniqueness_ratio': (unique / samples) * 100 if samples else 0
        }


# Convenience function
def generate_from_grammar(grammar: Dict[str, List], count: int = 1,
                         start_symbol: str = None) -> List[str]:
    """
    Quick function to generate from grammar.

    Args:
        grammar: Parsed grammar rules
        count: Number of strings to generate
        start_symbol: Starting rule

    Returns:
        List of generated strings

    Example:
        >>> grammar = parse_grammar(grammar_text)
        >>> strings = generate_from_grammar(grammar, count=10)
    """
    generator = GrammarGenerator(grammar)
    return generator.generate_batch(count, start_symbol)


# Testing
if __name__ == "__main__":
    from grammar_parser import GrammarParser

    # Test grammar
    test_grammar = """
    <expr> ::= <term> | <expr> "+" <term>
    <term> ::= <number> | "(" <expr> ")"
    <number> ::= <digit> {<digit>}
    <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
    """

    # Parse grammar
    parser = GrammarParser()
    grammar = parser.parse(test_grammar)

    # Generate strings
    generator = GrammarGenerator(grammar, max_depth=5)

    print("Generated expressions:")
    for i in range(10):
        expr = generator.generate("expr")
        print(f"  {i+1}. {expr}")

    # Statistics
    stats = generator.get_statistics(samples=100)
    print(f"\nGeneration statistics (100 samples):")
    print(f"  Avg length:      {stats['avg_length']:.1f}")
    print(f"  Length range:    {stats['min_length']}-{stats['max_length']}")
    print(f"  Unique outputs:  {stats['unique_count']}")
    print(f"  Uniqueness:      {stats['uniqueness_ratio']:.1f}%")
