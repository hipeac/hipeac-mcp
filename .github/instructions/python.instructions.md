---
applyTo: "**/*.py"
description: Python, MCP, and Pytest coding standards for the project.
---

## General

- All code must be PEP 8 compliant.
- All function signatures must use type hints.

## Docstring format (reStructuredText)

- All public functions, methods, and modules **must** have a docstring.
- The format must be reStructuredText (reST) to be compatible with Sphinx.
- Provide clear descriptions for parameters, return values, and any exceptions raised.
- Do not include type information, as it is already in the function signature.
- All `:param`, `:returns`, and `:raises` descriptions must end with a period (`.`) for consistency.

  > ```python
  > def get_user_by_id(user_id: int, is_active: bool = True) -> User | None:
  >     """Fetch a user from the database by their primary key.
  >
  >     :param user_id: The primary key of the user to retrieve.
  >     :param is_active: If True, only search for active users.
  >     :returns: The User object or None if not found.
  >     :raises User.DoesNotExist: If no user with the given ID is found.
  >     """
  >     # ... function implementation ...
  >     pass
  > ```

## Testing (pytest)

- All new code requires tests.
- Structure tests using the Arrange-Act-Assert (AAA) pattern.
- Use `@pytest.fixture` for setup and `@pytest.mark.parametrize` for testing multiple inputs.

### Test-review workflow

When asked to review, audit, or add tests to an existing codebase, always apply this sequence:

1. **Read the tests first.** Critically evaluate each test for correctness, completeness, and false confidence:
   - Does the assertion actually verify the claimed behaviour, or is it trivially true?
   - Are edge cases and failure paths covered, not just the happy path?
   - Are there implicit assumptions about data or timing that could make the test fragile?
2. **Adjust the tests** to fix any identified weaknesses before running them.
3. **Run the adjusted suite.** A failing test after adjustment is valuable: it reveals a real bug in the production code.
4. **Fix the production code** to make failing tests pass — never weaken a test to force it green.

## Command execution (CRITICAL)

- Rule: all Python commands **must be prefixed with `./run`**.
- This is a required executable script in the project root that sets up the environment and runs commands within it.

- Correct examples:
  > ```bash
  > ./run python manage.py migrate
  > ./run pytest -k vision
  > ```
