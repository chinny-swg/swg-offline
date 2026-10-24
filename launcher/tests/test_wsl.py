import unittest
from pathlib import PureWindowsPath

from swg_offline import wsl


class WslTest(unittest.TestCase):
    def test_to_wsl_path(self):
        self.assertEqual(wsl.to_wsl_path(r"C:\Users\Me\AppData\Local\SWGOffline\overrides"),
                         "/mnt/c/Users/Me/AppData/Local/SWGOffline/overrides")
        self.assertEqual(wsl.to_wsl_path("D:\\"), "/mnt/d")
        with self.assertRaises(ValueError):
            wsl.to_wsl_path(r"\\server\share\x")

    def test_mirrored_networking(self):
        self.assertTrue(wsl.mirrored_networking("[wsl2]\nnetworkingMode=mirrored\n"))
        self.assertTrue(wsl.mirrored_networking("[wsl2]\r\nmemory=8GB\r\nnetworkingMode = Mirrored\r\n"))
        self.assertFalse(wsl.mirrored_networking("[wsl2]\nnetworkingMode=nat\n"))
        self.assertFalse(wsl.mirrored_networking(""))
        self.assertFalse(wsl.mirrored_networking("not ini at all ["))

    def test_first_ipv4(self):
        self.assertEqual(wsl.first_ipv4("fe80::1 172.28.10.4 10.0.0.2 \n"), "172.28.10.4")
        self.assertIsNone(wsl.first_ipv4(""))

    def test_server_args(self):
        args = wsl.server_args("Debian", "172.28.10.4", PureWindowsPath(r"C:\X\overrides"), "player", 15)
        self.assertEqual(args[:6], ["wsl.exe", "-d", "Debian", "-u", "root", "--"])
        self.assertEqual(args[6], wsl.SERVER_COMMAND)
        self.assertIn("/mnt/c/X/overrides", args)
        self.assertEqual(args[-4:], ["--admin-user", "player", "--admin-level", "15"])


if __name__ == "__main__":
    unittest.main()
