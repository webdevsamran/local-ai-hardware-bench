"""Stable CLI exit codes for humans and CI.

Exit codes are part of the public automation contract. Scripts must be
able to distinguish success, validation failures, usage errors,
incomparable comparisons, and configuration issues without parsing
stderr.
"""

EXIT_OK = 0
EXIT_VALIDATION_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_NOT_COMPARABLE = 3
EXIT_CONFIGURATION_ERROR = 4
EXIT_REGRESSION_DETECTED = 5
EXIT_INTERNAL_ERROR = 130

EXIT_CODE_NAMES = {
    EXIT_OK: "OK",
    EXIT_VALIDATION_ERROR: "VALIDATION_ERROR",
    EXIT_USAGE_ERROR: "USAGE_ERROR",
    EXIT_NOT_COMPARABLE: "NOT_COMPARABLE",
    EXIT_CONFIGURATION_ERROR: "CONFIGURATION_ERROR",
    EXIT_REGRESSION_DETECTED: "REGRESSION_DETECTED",
    EXIT_INTERNAL_ERROR: "INTERNAL_ERROR",
}
