from pathlib import Path
import unittest


class ReducedMotionTests(unittest.TestCase):
    def test_reduced_motion_disables_infinite_animations(self):
        css = Path('zorbit/studio_ui/styles.css').read_text(encoding='utf-8')
        rule = css.split('@media (prefers-reduced-motion: reduce) {', 2)[-1].split('}', 1)[0]
        self.assertIn('animation: none !important', rule, 'reduced motion should stop animations')


if __name__ == '__main__':
    unittest.main()
