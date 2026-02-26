Feature: Initialize assessment

  Scenario: Create report files and Kanbus structure
    Given cached questions
    And a target repo path
    When I run wai init
    Then a new assessment folder and Kanbus files are created
