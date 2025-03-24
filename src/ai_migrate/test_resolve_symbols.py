import pytest
from ai_migrate.resolve_symbols import contains_definition


@pytest.mark.parametrize(
    "line, symbol, expected",
    [
        # Class definitions
        ("public class MyClass", "MyClass", True),
        ("class MyClass", "MyClass", True),
        ("public class MyOtherClass", "MyClass", False),
        # Generic class definitions
        ("data class EndFlowAction<out TString>", "EndFlowAction", True),
        ("class GenericClass<T>", "GenericClass", True),
        ("class GenericClass<T>", "OtherClass", False),
        # Interface definitions
        ("interface MyInterface", "MyInterface", True),
        ("interface MyOtherInterface", "MyInterface", False),
        # Method definitions
        ("public void myMethod()", "myMethod", True),
        ("int getValue()", "getValue", True),
        ("void anotherMethod()", "myMethod", False),
        # Mixed modifiers and keywords
        ("private final class MixedClass", "MixedClass", True),
        ("public static void main(String[] args)", "main", True),
        ("enum MyEnum { VALUE1, VALUE2 }", "MyEnum", True),
        ("enum MyEnum { VALUE1, VALUE2 }", "OtherEnum", False),
        # Edge cases
        ("data class Empty<out T>()", "Empty", True),
        ("data class NotEmpty<out T>()", "Other", False),
        ("class MyClass /* comment */", "MyClass", True),
        ("public static String myStaticMethod()", "myStaticMethod", True),
    ],
)
def test_contains_definition(line, symbol, expected):
    assert contains_definition(line, symbol) == expected


if __name__ == "__main__":
    pytest.main()
