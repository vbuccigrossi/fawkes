"""
Built-in Grammars

Pre-defined grammars for common file formats and protocols.
"""

from typing import Dict


class BuiltinGrammars:
    """Collection of built-in grammar specifications."""

    @staticmethod
    def get_json_grammar() -> str:
        """Get JSON grammar (simplified)."""
        return """
        <json> ::= <object> | <array>
        <object> ::= "{" [<members>] "}"
        <members> ::= <pair> | <pair> "," <members>
        <pair> ::= <string> ":" <value>
        <array> ::= "[" [<elements>] "]"
        <elements> ::= <value> | <value> "," <elements>
        <value> ::= <string> | <number> | <object> | <array> | "true" | "false" | "null"
        <string> ::= '"' {<char>} '"'
        <number> ::= ["-"] <digits> ["." <digits>]
        <digits> ::= <digit> {<digit>}
        <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
        <char> ::= "a" | "b" | "c" | "d" | "e" | "f" | "g" | "h" | "i" | "j" | "k" | "l" | "m" | "n" | "o" | "p" | "q" | "r" | "s" | "t" | "u" | "v" | "w" | "x" | "y" | "z" | "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "I" | "J" | "K" | "L" | "M" | "N" | "O" | "P" | "Q" | "R" | "S" | "T" | "U" | "V" | "W" | "X" | "Y" | "Z" | "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | " " | "_"
        """

    @staticmethod
    def get_xml_grammar() -> str:
        """Get XML grammar (simplified)."""
        return """
        <document> ::= <element>
        <element> ::= "<" <tag> [<attributes>] ">" [<content>] "</" <tag> ">" | "<" <tag> [<attributes>] "/>"
        <tag> ::= <letter> {<letter_or_digit>}
        <attributes> ::= <attribute> {<attribute>}
        <attribute> ::= <name> "=" '"' {<char>} '"'
        <content> ::= <text> | <element> | <text> <element> <content>
        <text> ::= <char> {<char>}
        <name> ::= <letter> {<letter_or_digit>}
        <letter> ::= "a" | "b" | "c" | "d" | "e" | "f" | "g" | "h" | "i" | "j" | "k" | "l" | "m" | "n" | "o" | "p" | "q" | "r" | "s" | "t" | "u" | "v" | "w" | "x" | "y" | "z"
        <letter_or_digit> ::= <letter> | <digit>
        <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
        <char> ::= "a" | "b" | "c" | "x" | "y" | "z" | "0" | "1" | "2" | " "
        """

    @staticmethod
    def get_sql_grammar() -> str:
        """Get SQL grammar (simplified SELECT statements)."""
        return """
        <query> ::= "SELECT" <columns> "FROM" <table> [<where>] [<order>]
        <columns> ::= "*" | <column_list>
        <column_list> ::= <column> | <column> "," <column_list>
        <column> ::= <identifier>
        <table> ::= <identifier>
        <where> ::= "WHERE" <condition>
        <condition> ::= <column> <operator> <value>
        <operator> ::= "=" | ">" | "<" | ">=" | "<=" | "!=" | "LIKE"
        <value> ::= <number> | <string>
        <order> ::= "ORDER BY" <column> [<direction>]
        <direction> ::= "ASC" | "DESC"
        <identifier> ::= <letter> {<letter_or_digit>}
        <string> ::= "'" {<char>} "'"
        <number> ::= <digit> {<digit>}
        <letter> ::= "a" | "b" | "c" | "d" | "e" | "f" | "x" | "y" | "z"
        <letter_or_digit> ::= <letter> | <digit>
        <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
        <char> ::= "a" | "b" | "c" | "x" | "y" | "z" | "0" | "1" | " "
        """

    @staticmethod
    def get_url_grammar() -> str:
        """Get URL grammar."""
        return """
        <url> ::= <scheme> "://" <host> [":" <port>] [<path>] [<query>] [<fragment>]
        <scheme> ::= "http" | "https" | "ftp" | "file"
        <host> ::= <hostname> | <ipv4>
        <hostname> ::= <label> {"." <label>}
        <label> ::= <letter> {<letter_or_digit>}
        <ipv4> ::= <octet> "." <octet> "." <octet> "." <octet>
        <octet> ::= <digit> | <digit> <digit> | <digit> <digit> <digit>
        <port> ::= <digit> {<digit>}
        <path> ::= "/" {<segment>}
        <segment> ::= <letter_or_digit> {<letter_or_digit>} ["/"]
        <query> ::= "?" <param> {"&" <param>}
        <param> ::= <name> "=" <value>
        <fragment> ::= "#" {<letter_or_digit>}
        <name> ::= <letter> {<letter_or_digit>}
        <value> ::= {<letter_or_digit>}
        <letter> ::= "a" | "b" | "c" | "d" | "e" | "f" | "g" | "h" | "i" | "j" | "k" | "l" | "m" | "n" | "o" | "p" | "q" | "r" | "s" | "t" | "u" | "v" | "w" | "x" | "y" | "z"
        <letter_or_digit> ::= <letter> | <digit> | "_" | "-"
        <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
        """

    @staticmethod
    def get_arithmetic_grammar() -> str:
        """Get arithmetic expression grammar."""
        return """
        <expr> ::= <term> | <expr> "+" <term> | <expr> "-" <term>
        <term> ::= <factor> | <term> "*" <factor> | <term> "/" <factor>
        <factor> ::= <number> | "(" <expr> ")"
        <number> ::= <digit> {<digit>}
        <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
        """

    @staticmethod
    def get_email_grammar() -> str:
        """Get email address grammar."""
        return """
        <email> ::= <local> "@" <domain>
        <local> ::= <word> {"." <word>}
        <domain> ::= <label> {"." <label>}
        <word> ::= <letter> {<letter_or_digit>}
        <label> ::= <letter> {<letter_or_digit>}
        <letter> ::= "a" | "b" | "c" | "d" | "e" | "f" | "g" | "h" | "i" | "j" | "k" | "l" | "m" | "n" | "o" | "p" | "q" | "r" | "s" | "t" | "u" | "v" | "w" | "x" | "y" | "z"
        <letter_or_digit> ::= <letter> | <digit> | "_" | "-"
        <digit> ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
        """

    @staticmethod
    def get_grammar(name: str) -> str:
        """
        Get grammar by name.

        Args:
            name: Grammar name (json, xml, sql, url, arithmetic, email)

        Returns:
            Grammar text
        """
        grammars = {
            'json': BuiltinGrammars.get_json_grammar,
            'xml': BuiltinGrammars.get_xml_grammar,
            'sql': BuiltinGrammars.get_sql_grammar,
            'url': BuiltinGrammars.get_url_grammar,
            'arithmetic': BuiltinGrammars.get_arithmetic_grammar,
            'email': BuiltinGrammars.get_email_grammar,
        }

        if name.lower() not in grammars:
            raise ValueError(f"Unknown grammar: {name}. Available: {list(grammars.keys())}")

        return grammars[name.lower()]()

    @staticmethod
    def list_grammars() -> list:
        """List available built-in grammars."""
        return ['json', 'xml', 'sql', 'url', 'arithmetic', 'email']


# Testing
if __name__ == "__main__":
    from grammar_parser import GrammarParser
    from generator import GrammarGenerator

    print("Available built-in grammars:")
    for grammar_name in BuiltinGrammars.list_grammars():
        print(f"  - {grammar_name}")

    # Test JSON grammar
    print("\n" + "=" * 60)
    print("Testing JSON Grammar")
    print("=" * 60)

    json_grammar = BuiltinGrammars.get_json_grammar()
    parser = GrammarParser()
    rules = parser.parse(json_grammar)

    generator = GrammarGenerator(rules, max_depth=4)

    print("\nGenerated JSON samples:")
    for i in range(5):
        json_str = generator.generate("json")
        print(f"  {i+1}. {json_str}")

    # Test URL grammar
    print("\n" + "=" * 60)
    print("Testing URL Grammar")
    print("=" * 60)

    url_grammar = BuiltinGrammars.get_url_grammar()
    rules = parser.parse(url_grammar)
    generator = GrammarGenerator(rules, max_depth=5)

    print("\nGenerated URLs:")
    for i in range(5):
        url = generator.generate("url")
        print(f"  {i+1}. {url}")

    # Test SQL grammar
    print("\n" + "=" * 60)
    print("Testing SQL Grammar")
    print("=" * 60)

    sql_grammar = BuiltinGrammars.get_sql_grammar()
    rules = parser.parse(sql_grammar)
    generator = GrammarGenerator(rules, max_depth=4)

    print("\nGenerated SQL queries:")
    for i in range(5):
        query = generator.generate("query")
        print(f"  {i+1}. {query}")
