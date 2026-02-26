Feature: Sync answers to Kanbus

  Scenario: Post answers and update task status
    Given an initialized assessment
    And an answered question
    When I run wai sync-kanbus
    Then Kanbus tasks are commented and closed accordingly
