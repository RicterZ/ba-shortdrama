import sys
import unittest
from unittest.mock import patch
import render


class RenderTest(unittest.TestCase):
    def test_preview_reduces_work(self):
        profile = render.PROFILES['preview']
        self.assertEqual(profile['scale'], '0.5')
        self.assertEqual(profile['frame_step'], 3)
        self.assertEqual(30 / profile['frame_step'], 10)
        self.assertEqual(5400 / 30, (5400 / profile['frame_step']) / 10)

    def test_default_only_video(self):
        with patch.object(sys, 'argv', ['render.py', '--episode', 'test']):
            self.assertEqual(render.parse_args().mode, 'video')

    def test_failure_propagates(self):
        import subprocess
        with patch('render.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'test')):
            with self.assertRaises(subprocess.CalledProcessError):
                render.run(['test'])


if __name__ == '__main__':
    unittest.main()
