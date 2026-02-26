Feature: Fetch Well-Architected questions

  Scenario: Fetch and cache official questions
    Given sample AWS pages
    When I run wai fetch
    Then the questions cache is created with entries for all pillars
