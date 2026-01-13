"""
Grammar Mutator

Mutates grammar-generated strings for coverage-guided fuzzing.
"""

import random
import logging
from typing import List


logger = logging.getLogger("fawkes.grammar.mutator")


class GrammarMutator:
    """
    Mutates grammar-generated strings.

    Combines grammar-based generation with mutation fuzzing
    for better coverage.

    Mutation strategies:
    - Insert random characters
    - Delete characters
    - Flip bits
    - Repeat sections
    - Splice with other inputs
    """

    def __init__(self, mutation_rate: float = 0.1):
        """
        Initialize grammar mutator.

        Args:
            mutation_rate: Probability of mutation per character
        """
        self.mutation_rate = mutation_rate
        self.logger = logging.getLogger("fawkes.grammar.mutator")

    def mutate(self, input_str: str, mutations: int = None) -> str:
        """
        Mutate string.

        Args:
            input_str: Input string to mutate
            mutations: Number of mutations (default: based on mutation_rate)

        Returns:
            Mutated string
        """
        if not input_str:
            return input_str

        # Convert to list for easier mutation
        chars = list(input_str)

        # Determine number of mutations
        if mutations is None:
            mutations = max(1, int(len(chars) * self.mutation_rate))

        # Perform mutations
        for _ in range(mutations):
            mutation_type = random.choice([
                'insert',
                'delete',
                'flip',
                'repeat',
                'replace'
            ])

            if mutation_type == 'insert':
                self._mutate_insert(chars)
            elif mutation_type == 'delete':
                self._mutate_delete(chars)
            elif mutation_type == 'flip':
                self._mutate_flip(chars)
            elif mutation_type == 'repeat':
                self._mutate_repeat(chars)
            elif mutation_type == 'replace':
                self._mutate_replace(chars)

        return ''.join(chars)

    def _mutate_insert(self, chars: List[str]):
        """Insert random character at random position."""
        if not chars:
            return

        pos = random.randint(0, len(chars))
        char = self._random_char()
        chars.insert(pos, char)

    def _mutate_delete(self, chars: List[str]):
        """Delete random character."""
        if len(chars) <= 1:
            return

        pos = random.randint(0, len(chars) - 1)
        del chars[pos]

    def _mutate_flip(self, chars: List[str]):
        """Flip random bit in random character."""
        if not chars:
            return

        pos = random.randint(0, len(chars) - 1)
        char_code = ord(chars[pos])

        # Flip random bit
        bit = random.randint(0, 7)
        char_code ^= (1 << bit)

        # Keep printable if possible
        if 32 <= char_code <= 126:
            chars[pos] = chr(char_code)

    def _mutate_repeat(self, chars: List[str]):
        """Repeat random section."""
        if len(chars) < 2:
            return

        # Select random section
        start = random.randint(0, len(chars) - 2)
        end = random.randint(start + 1, min(start + 10, len(chars)))

        section = chars[start:end]

        # Insert repeated section at random position
        insert_pos = random.randint(0, len(chars))
        chars[insert_pos:insert_pos] = section

    def _mutate_replace(self, chars: List[str]):
        """Replace random character."""
        if not chars:
            return

        pos = random.randint(0, len(chars) - 1)
        chars[pos] = self._random_char()

    def _random_char(self) -> str:
        """Generate random character."""
        # Biased towards printable ASCII
        if random.random() < 0.8:
            return chr(random.randint(32, 126))  # Printable ASCII
        else:
            return chr(random.randint(0, 255))  # Any byte

    def mutate_batch(self, inputs: List[str], count: int = None) -> List[str]:
        """
        Mutate batch of inputs.

        Args:
            inputs: List of input strings
            count: Number of mutations to generate (default: len(inputs))

        Returns:
            List of mutated strings
        """
        if not inputs:
            return []

        if count is None:
            count = len(inputs)

        mutated = []
        for _ in range(count):
            # Select random input
            input_str = random.choice(inputs)

            # Mutate it
            mutated_str = self.mutate(input_str)
            mutated.append(mutated_str)

        return mutated

    def crossover(self, input1: str, input2: str) -> str:
        """
        Perform crossover between two inputs.

        Args:
            input1: First input
            input2: Second input

        Returns:
            Crossover result
        """
        if not input1 or not input2:
            return input1 or input2

        # Single-point crossover
        point1 = random.randint(0, len(input1))
        point2 = random.randint(0, len(input2))

        # Combine parts
        result = input1[:point1] + input2[point2:]

        return result

    def smart_mutate(self, input_str: str, interesting_bytes: List[int] = None) -> str:
        """
        Smart mutation targeting interesting bytes.

        Args:
            input_str: Input string
            interesting_bytes: List of byte values to favor

        Returns:
            Mutated string
        """
        if interesting_bytes is None:
            interesting_bytes = [0, 255, 0x7f, 0x80, 0xff]

        chars = list(input_str)

        # Perform targeted mutations
        mutations = max(1, int(len(chars) * self.mutation_rate))

        for _ in range(mutations):
            if not chars:
                break

            pos = random.randint(0, len(chars) - 1)

            # Use interesting byte
            if random.random() < 0.5 and interesting_bytes:
                byte_val = random.choice(interesting_bytes)
                chars[pos] = chr(byte_val & 0xFF)
            else:
                # Regular mutation
                mutation_type = random.choice(['insert', 'delete', 'flip', 'replace'])

                if mutation_type == 'insert':
                    self._mutate_insert(chars)
                elif mutation_type == 'delete':
                    self._mutate_delete(chars)
                elif mutation_type == 'flip':
                    self._mutate_flip(chars)
                elif mutation_type == 'replace':
                    self._mutate_replace(chars)

        return ''.join(chars)


# Convenience functions
def mutate_string(input_str: str, mutation_rate: float = 0.1) -> str:
    """
    Quick function to mutate string.

    Args:
        input_str: String to mutate
        mutation_rate: Mutation rate

    Returns:
        Mutated string

    Example:
        >>> original = '{"key": "value"}'
        >>> mutated = mutate_string(original)
    """
    mutator = GrammarMutator(mutation_rate=mutation_rate)
    return mutator.mutate(input_str)


# Testing
if __name__ == "__main__":
    # Test mutation
    original = '{"name": "test", "value": 123}'

    print("Original string:")
    print(f"  {original}")

    mutator = GrammarMutator(mutation_rate=0.2)

    print("\nMutated versions:")
    for i in range(10):
        mutated = mutator.mutate(original)
        print(f"  {i+1}. {mutated}")

    # Test crossover
    input1 = '{"key1": "value1"}'
    input2 = '{"key2": 999}'

    print("\nCrossover:")
    print(f"  Input 1: {input1}")
    print(f"  Input 2: {input2}")
    print(f"  Result:  {mutator.crossover(input1, input2)}")

    # Test smart mutation
    print("\nSmart mutation (targeting interesting bytes):")
    for i in range(5):
        mutated = mutator.smart_mutate(original)
        print(f"  {i+1}. {mutated}")
