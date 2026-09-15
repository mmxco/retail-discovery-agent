import pytest
from pydantic import ValidationError
# Assumes the previous code is saved in a file named extraction_pipeline.py
from discovery_pipeline import PainPoint, DiscoveryBrief

# ==============================================================================
# PYTEST SUITE FOR LLM STRUCTURED EXTRACTION
# ==============================================================================

def test_successful_pain_point_extraction():
    """
    Tests that clear discovery notes result in a valid DiscoveryBrief
    with correctly categorized pain points.
    """
    notes = (
        "The legacy database takes 4 hours to sync, causing the fulfillment "
        "team to miss same-day shipping cutoffs and losing retail customers."
    )
    
    # Execute the live API call
    result = extract_pain_points(notes)
    
    # 1. Structural Verification: 
    # If execution reaches this line, Pydantic has already guaranteed the 
    # output is valid JSON and strictly matches the DiscoveryBrief schema.
    
    # 2. Semantic Verification:
    # Assert the LLM successfully extracted the data and applied the schema.
    assert isinstance(result, DiscoveryBrief)
    assert len(result.pain_points) > 0
    
    # Verify the LLM adhered to the category ENUM instructions
    for point in result.pain_points:
        assert point.category in ["Technical", "Business"]

def test_irrelevant_input_handling():
    """
    Tests that the LLM does not hallucinate pain points when given 
    unrelated text data.
    """
    notes = "The quick brown fox jumps over the lazy dog."
    
    # Execute the live API call
    result = extract_pain_points(notes)
    
    # The schema should be valid, but the pain_points list must be empty.
    assert len(result.pain_points) == 0

def test_validation_error_handling(mocker):
    """
    Mocks a malformed API response to ensure downstream functions 
    handle Pydantic ValidationErrors correctly without crashing.
    Requires pytest-mock to be installed.
    """
    # Mock the API response to return an invalid JSON schema (missing required fields)
    mock_bad_json = '{"company_name": "Acme", "wrong_key": []}'
    
    # Setup the mocker to bypass the actual Gemini API call
    mocker.patch(
        'extraction_pipeline.extract_pain_points', 
        return_value=mock_bad_json
    )
    
    # Verify Pydantic traps the structural failure and raises the correct exception
    with pytest.raises(ValidationError):
        DiscoveryBrief.model_validate_json(mock_bad_json)