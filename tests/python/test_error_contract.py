import unittest

from runtime.cu_runtime.errors import ComputerUseError


class ErrorContractTest(unittest.TestCase):
    def test_error_serializes_stable_code_and_details(self):
        error = ComputerUseError(
            "stale_state",
            "Element no longer matches the captured state",
            {"app": "com.apple.calculator", "windowId": 42},
        )
        self.assertEqual(
            {
                "code": "stale_state",
                "message": "Element no longer matches the captured state",
                "details": {"app": "com.apple.calculator", "windowId": 42},
            },
            error.to_dict(),
        )
