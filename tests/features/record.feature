Feature: Record interview answers

  Scenario: Update a question with a human answer
    Given an initialized assessment
    When I run wai record-answer
    Then the report is updated with status and answer
