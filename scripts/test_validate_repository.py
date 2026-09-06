"""Regression tests for repository validation helpers."""

import importlib.util
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock


SCRIPT = Path(__file__).with_name("validate_repository.py")
SPEC = importlib.util.spec_from_file_location("validate_repository", SCRIPT)
assert SPEC and SPEC.loader
validate_repository = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_repository)


class ExportRelativePathTests(unittest.TestCase):
    def test_uses_posix_separator_for_windows_path(self) -> None:
        export = PureWindowsPath(r"C:\export")
        exported_file = export / "prompts" / "maker.md"

        self.assertEqual(
            validate_repository.export_relative_path(exported_file, export),
            "prompts/maker.md",
        )

    def test_validate_export_uses_posix_path_helper_for_nested_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            source = repository / "prompts" / "maker.md"
            source.parent.mkdir()
            source.write_bytes(b"test content")

            with (
                mock.patch.object(validate_repository, "ROOT", repository),
                mock.patch.object(
                    validate_repository,
                    "export_relative_path",
                    wraps=validate_repository.export_relative_path,
                ) as export_relative_path,
            ):
                validate_repository.validate_export(["prompts/maker.md"])

            export_relative_path.assert_called_once()


if __name__ == "__main__":
    unittest.main()
