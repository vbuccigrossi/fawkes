"""
Fawkes Grammar-Based Fuzzing

Generates structurally valid inputs from grammar specifications,
enabling effective fuzzing of parsers, compilers, and protocol implementations.

Features:
- Grammar parser (BNF/EBNF support)
- Context-free grammar generation
- Mutation-based grammar fuzzing
- Built-in grammars (JSON, XML, SQL, etc.)
"""

from .grammar_parser import GrammarParser
from .generator import GrammarGenerator
from .mutator import GrammarMutator
from .builtin_grammars import BuiltinGrammars

__all__ = ['GrammarParser', 'GrammarGenerator', 'GrammarMutator', 'BuiltinGrammars']
