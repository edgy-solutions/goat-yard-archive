import pytest
import sys
from pathlib import Path

# Add the pipeline/scripts directory to sys.path so we can import the normalizer
scripts_dir = Path(__file__).parent.parent / "pipeline" / "scripts"
sys.path.append(str(scripts_dir))

from normalize_markdown import verify_normalization

def test_verify_normalization_catches_truncation():
    """
    Test that the verify_normalization function catches when the LLM truncates
    the end of the source text.
    """
    source_text = """
Ver. 1. This is the first verse commentary. It has a lot of words so it passes the length check.
It continues for a bit to make sure it's substantial enough.

Ver. 2. This is the second verse commentary. It also has a lot of words and explains things.
It is very important that this part is preserved.

Ver. 3. This is the final verse commentary. It contains the conclusion of the page.
If this is missing, the verification should definitely fail and flag it as truncated.
"""

    # The LLM output is truncated and misses Ver. 3
    truncated_output = """
Ver. 1. This is the first verse commentary. It has a lot of words so it passes the length check.
It continues for a bit to make sure it's substantial enough.

Ver. 2. This is the second verse commentary. It also has a lot of words and explains things.
It is very important that this part is preserved.
"""

    # Verify
    result = verify_normalization(source_text, truncated_output)
    
    # It should not pass
    assert not result.passed, "Verification should fail when output is truncated"
    
    # It should have an unauthorized change indicating truncation
    truncation_error_found = False
    for change in result.unauthorized_changes:
        if change.get('type') == 'content_removed' and 'End of source not found' in change.get('note', ''):
            truncation_error_found = True
            break
            
    assert truncation_error_found, "Verification should specifically flag the end of source as missing"

def test_verify_normalization_passes_full_text():
    """
    Test that the verify_normalization function passes when the text is fully preserved.
    """
    source_text = """
Ver. 1. This is the first verse commentary. It has a lot of words so it passes the length check.
It continues for a bit to make sure it's substantial enough.

Ver. 2. This is the second verse commentary. It also has a lot of words and explains things.
It is very important that this part is preserved.

Ver. 3. This is the final verse commentary. It contains the conclusion of the page.
If this is missing, the verification should definitely fail and flag it as truncated.
"""

    # The LLM output preserves everything
    full_output = """
Ver. 1. This is the first verse commentary. It has a lot of words so it passes the length check.
It continues for a bit to make sure it's substantial enough.

Ver. 2. This is the second verse commentary. It also has a lot of words and explains things.
It is very important that this part is preserved.

Ver. 3. This is the final verse commentary. It contains the conclusion of the page.
If this is missing, the verification should definitely fail and flag it as truncated.
"""

    # Verify
    result = verify_normalization(source_text, full_output)
    
    # It should pass
    assert result.passed, f"Verification should pass when output is complete. Errors: {result.unauthorized_changes}"
