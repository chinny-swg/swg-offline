import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from swg_offline import presets
from swg_offline.settings import Settings


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def test_tuned_solo_files(self):
        settings = Settings(zones=["tutorial", "naboo"])
        presets.render(presets.PRESETS["tuned-solo"], settings, self.dir)
        config = (self.dir / "config-offline.lua").read_text()
        player = (self.dir / "player_manager-local.lua").read_text()
        loot = (self.dir / "loot_manager-local.lua").read_text()
        self.assertIn('ZonesEnabled = { "tutorial", "naboo" }', config)
        self.assertIn("SpaceZonesEnabled = {}", config)
        self.assertIn("MakeWeb = 0", config)
        self.assertIn("globalExpMultiplier = 4.0", player)
        self.assertIn("yellowChance = 500", loot)

    def test_faithful_overrides_nothing(self):
        presets.render(presets.PRESETS["faithful"], Settings(), self.dir)
        for name in ("player_manager-local.lua", "loot_manager-local.lua"):
            body = [l for l in (self.dir / name).read_text().splitlines() if not l.startswith("--")]
            self.assertEqual(body, [], name)

    def test_only_sandbox_is_admin(self):
        self.assertEqual([p.key for p in presets.PRESETS.values() if p.admin], ["sandbox"])

    def test_lua_string_escaping(self):
        self.assertEqual(presets._lua_value('a"b\\c'), '"a\\"b\\\\c"')

    @unittest.skipUnless(shutil.which("lua5.3"), "lua5.3 not installed")
    def test_rendered_files_are_valid_lua(self):
        for preset in presets.PRESETS.values():
            presets.render(preset, Settings(), self.dir)
            for path in self.dir.glob("*.lua"):
                subprocess.run(["lua5.3", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
