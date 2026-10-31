from pathlib import Path
import unittest


class TestReducedMotion(unittest.TestCase):
    def test_reduced_motion_disables_infinite_animations(self):
        stylesheet = Path(__file__).resolve().parents[1] / 'zorbit' / 'studio_ui' / 'styles.css'
        css = stylesheet.read_text(encoding='utf-8')
        rule = css.rsplit('@media (prefers-reduced-motion: reduce) {', 1)[-1].split('}', 1)[0]
        self.assertIn(
            'animation: none !important',
            rule,
            'reduced motion should stop animations',
        )


if __name__ == '__main__':
    unittest.main()
