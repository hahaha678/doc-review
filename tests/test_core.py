import json
import tempfile
import unittest
from pathlib import Path

from doc_review.core import ReviewError, acknowledge, load_config, scan


class ReviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "docs").mkdir()
        self.source = self.root / "docs" / "intro.md"
        self.translation = self.root / "docs" / "intro.zh.md"
        self.source.write_text("# Intro\n\n## Install\nRun this.\n", encoding="utf-8")
        self.translation.write_text("# 简介\n\n## 安装\n运行它。\n", encoding="utf-8")
        self.config = self.root / "doc-review.json"
        self.config.write_text(json.dumps({"version": 1, "pairs": [{"id": "intro", "source": "docs/intro.md", "translation": "docs/intro.zh.md"}]}), encoding="utf-8")

    def test_review_lifecycle_and_changed_heading(self):
        self.assertEqual(scan(self.config)["pairs"][0]["status"], "unreviewed")
        acknowledge(self.config, "intro", "Tester", "Checked both files")
        self.assertEqual(scan(self.config)["pairs"][0]["status"], "current")
        self.source.write_text("# Intro\n\n## Install\nRun this command.\n", encoding="utf-8")
        result = scan(self.config)["pairs"][0]
        self.assertEqual(result["status"], "source_changed")
        self.assertEqual(result["changed_sections"], ["## Install"])
        self.translation.write_text("# 简介\n\n## 安装\n运行此命令。\n", encoding="utf-8")
        self.assertEqual(scan(self.config)["pairs"][0]["status"], "both_changed")
        acknowledge(self.config, "intro", "Tester", "Updated installation translation")
        self.assertEqual(scan(self.config)["action_required"], 0)
        self.translation.write_text("# 简介\n\n## 安装\n运行此命令！\n", encoding="utf-8")
        self.assertEqual(scan(self.config)["pairs"][0]["status"], "translation_changed")

    def test_missing_file_and_rename_need_review(self):
        acknowledge(self.config, "intro", "Tester", "Initial review")
        self.translation.unlink()
        self.assertEqual(scan(self.config)["pairs"][0]["status"], "missing_translation")
        with self.assertRaises(ReviewError):
            acknowledge(self.config, "intro", "Tester", "Cannot approve absent file")
        self.translation.write_text("# 简介\n\n## 安装\n运行它。\n", encoding="utf-8")
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["pairs"][0]["source"] = "docs/renamed.md"
        self.source.rename(self.root / "docs" / "renamed.md")
        self.config.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(scan(self.config)["pairs"][0]["status"], "unreviewed")

    def test_config_cannot_escape_root(self):
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["pairs"][0]["source"] = "../outside.md"
        self.config.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ReviewError):
            load_config(self.config)


if __name__ == "__main__":
    unittest.main()
