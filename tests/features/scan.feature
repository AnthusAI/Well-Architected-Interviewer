Feature: Scan and apply evidence

  Scenario: Apply scan evidence to reports
    Given an initialized assessment
    And a target repo path
    When I run wai scan
    And I run wai apply-evidence
    Then evidence blocks are populated and status is partial
