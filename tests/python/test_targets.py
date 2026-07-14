import unittest

from runtime.cu_runtime.errors import ComputerUseError
from runtime.cu_runtime.targets import AppRecord, MacWorkspace, TargetResolver


class FakeWorkspace:
    def __init__(self, apps):
        self.apps = apps
        self.launches = []

    def list_apps(self):
        return list(self.apps)

    def launch_without_activation(self, app):
        self.launches.append(app.bundle_id)


class FakeNativeWorkspace:
    def __init__(self):
        self.launch = None

    def launchApplicationAtURL_options_configuration_error_(
        self,
        url,
        options,
        configuration,
        error,
    ):
        self.launch = {
            "url": str(url.path()),
            "options": int(options),
            "configuration": dict(configuration),
            "error": error,
        }
        return True, None


class TargetResolverTest(unittest.TestCase):
    def setUp(self):
        self.calculator = AppRecord(
            bundle_id="com.apple.calculator",
            display_name="Calculator",
            path="/System/Applications/Calculator.app",
            pid=501,
            running=True,
        )
        self.workspace = FakeWorkspace([self.calculator])
        self.windows = [
            {
                "windowId": 9001,
                "pid": 501,
                "ownerName": "Calculator",
                "title": "Calculator",
                "layer": 0,
                "onScreen": True,
                "bounds": {"x": 120, "y": 80, "width": 230, "height": 408},
            },
            {
                "windowId": 9002,
                "pid": 501,
                "ownerName": "Calculator",
                "title": "Small panel",
                "layer": 0,
                "onScreen": True,
                "bounds": {"x": 0, "y": 0, "width": 20, "height": 20},
            },
        ]
        self.resolver = TargetResolver(self.workspace, lambda: list(self.windows))

    def test_resolves_by_bundle_name_and_path_without_activation(self):
        for identifier in [
            "com.apple.calculator",
            "Calculator",
            "/System/Applications/Calculator.app",
        ]:
            target = self.resolver.resolve(identifier)
            self.assertEqual("com.apple.calculator", target.bundle_id)
            self.assertEqual(501, target.pid)
            self.assertEqual(9001, target.window_id)
        self.assertEqual([], self.workspace.launches)

    def test_native_launch_uses_without_activation_and_async_options(self):
        native = FakeNativeWorkspace()
        workspace = MacWorkspace.__new__(MacWorkspace)
        workspace.workspace = native
        workspace.launch_without_activation(
            AppRecord(
                bundle_id="com.apple.Chess",
                display_name="Chess",
                path="/System/Applications/Chess.app",
                pid=None,
                running=False,
            )
        )
        self.assertEqual(
            {
                "url": "/System/Applications/Chess.app",
                "options": 0x00000200 | 0x00010000,
                "configuration": {},
                "error": None,
            },
            native.launch,
        )

    def test_resolves_explicit_window_id(self):
        target = self.resolver.resolve("Calculator", window_id=9002)
        self.assertEqual(9002, target.window_id)

    def test_lists_discoverable_window_ids_for_one_app(self):
        windows = self.resolver.list_windows("com.apple.calculator")
        self.assertEqual([9001, 9002], [window["windowId"] for window in windows])
        self.assertEqual({"x": 120, "y": 80, "width": 230, "height": 408}, windows[0]["bounds"])

    def test_rejects_missing_app_and_window(self):
        with self.assertRaises(ComputerUseError) as missing_app:
            self.resolver.resolve("Not Installed", launch=False)
        self.assertEqual("app_not_found", missing_app.exception.code)

        with self.assertRaises(ComputerUseError) as missing_window:
            self.resolver.resolve("Calculator", window_id=404)
        self.assertEqual("window_not_found", missing_window.exception.code)

    def test_revalidates_cached_target(self):
        target = self.resolver.resolve("Calculator")
        self.windows.clear()
        with self.assertRaises(ComputerUseError) as changed:
            self.resolver.revalidate(target)
        self.assertEqual("target_changed", changed.exception.code)

    def test_resolves_explicit_pid_for_controlled_test_process(self):
        workspace = FakeWorkspace([])
        resolver = TargetResolver(workspace, lambda: [
            {
                "windowId": 44,
                "pid": 123,
                "ownerName": "Python",
                "title": "Controlled Target",
                "layer": 0,
                "onScreen": True,
                "bounds": {"x": 10, "y": 20, "width": 300, "height": 200},
            }
        ])
        target = resolver.resolve("pid:123", launch=False)
        self.assertEqual(123, target.pid)
        self.assertEqual(44, target.window_id)
        self.assertEqual("pid:123", target.bundle_id)

    def test_explicit_pid_waits_for_window_registration(self):
        calls = 0

        def delayed_windows():
            nonlocal calls
            calls += 1
            if calls < 3:
                return []
            return [{
                "windowId": 45,
                "pid": 321,
                "ownerName": "Python",
                "title": "Delayed Target",
                "layer": 0,
                "onScreen": True,
                "bounds": {"x": 10, "y": 20, "width": 300, "height": 200},
            }]

        resolver = TargetResolver(FakeWorkspace([]), delayed_windows, process_checker=lambda pid: pid == 321)
        target = resolver.resolve("pid:321", launch=False, timeout=0.2)
        self.assertEqual(45, target.window_id)
        self.assertGreaterEqual(calls, 3)
