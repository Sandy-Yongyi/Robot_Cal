import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
from tools.linux_compat import linux_source_text
import deployment_check
import main

class LinuxCompatibilityTests(unittest.TestCase):
    def test_legacy_paths_are_converted_without_mutating_source(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('model/lidar/LidarCommon.py', 'model/dataprocess/complete_workpiece/DataFindBlocks.py', 'model/utils/LoggerUtil.py', 'control/LidarAcquisitionProcess.py', 'control/DataProcessingProcess.py', 'control/DataProcessWorker.py'):
            text = (root/name).read_text(encoding='utf-8-sig')
            converted = linux_source_text(text)
            self.assertNotEqual(text, converted, name)
            compile(converted, name, 'exec')
            self.assertNotIn('\\\\model\\\\tomls', converted, name)

    def test_linux_platform_plugin_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'platforms'
            path.mkdir()
            (path/'libqxcb.so').touch()
            self.assertTrue(deployment_check.check_linux_plugin(Path(directory), 'xcb').ok)
            self.assertFalse(deployment_check.check_linux_plugin(Path(directory), 'wayland').ok)

    def test_linux_duplicate_message_does_not_use_win32_api(self):
        with patch.object(main.sys,'platform','linux'), patch.object(main,'is_already_running',return_value=True), patch('main.prepare_environment'), patch('model.utils.TomlLoader.TomlLoader.load', return_value={'strategy_name':2}):
            with self.assertRaises(SystemExit): main.main()

    def test_export_linux_worker_converts_paths_and_keeps_private_sources_hidden(self):
        from tools.export_developer_package import export_package, protected_modules
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            binaries=Path(temp)/'binaries'
            for module, _ in protected_modules(root):
                file=binaries/(module.replace('.', '/')+'.cpython-311-x86_64-linux-gnu.so')
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'fixture')
            output=Path(temp)/'sdk'
            with patch('tools.export_developer_package.sys.platform','linux'):
                export_package(binaries, output, root)
            worker=(output/'control/DataProcessWorker.py').read_text(encoding='utf-8')
            self.assertIn('{self.config_dir}/ProcessConfig.toml', worker)
            self.assertFalse((output/'model/lidar/LidarCommon.py').exists())
            self.assertTrue(any((output/'model/lidar').glob('LidarCommon.*.so')))

    def test_linux_single_instance_retains_lock_and_detects_another_process(self):
        import sys
        fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock())
        handle = Mock()
        with patch.object(main.sys, 'platform', 'linux'), patch.dict(sys.modules, {'fcntl':fake_fcntl}), \
             patch.object(main.os, 'getuid', return_value=42, create=True), \
             patch.object(main, 'open', return_value=handle, create=True), patch.object(main, '_linux_lock', None):
            self.assertFalse(main.is_already_running())
            self.assertIs(main._linux_lock, handle)
            fake_fcntl.flock.assert_called_once_with(handle.fileno(), 6)
        fake_fcntl.flock = Mock(side_effect=BlockingIOError())
        with patch.object(main.sys, 'platform', 'linux'), patch.dict(sys.modules, {'fcntl':fake_fcntl}), \
             patch.object(main.os, 'getuid', return_value=42, create=True), \
             patch.object(main, 'open', return_value=handle, create=True), patch.object(main, '_linux_lock', None):
            self.assertTrue(main.is_already_running())
            handle.close.assert_called_once()

    def test_linux_build_script_uses_unix_line_endings(self):
        root=Path(__file__).resolve().parents[1]
        script=(root/'tools/build_linux.sh').read_bytes()
        self.assertNotIn(b'\r\n', script)
        self.assertTrue(script.startswith(b'#!/usr/bin/env bash\n'))
