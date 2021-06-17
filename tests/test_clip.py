import unittest

import numpy as np
from numpy.testing import assert_array_equal

from audiomentations.augmentations.transforms import Clip
from audiomentations.core.composition import Compose


class TestClip(unittest.TestCase):
    def test_single_channel(self):
        samples = np.array([0.5, 0.6, -0.2, 0.0], dtype=np.float32)
        sample_rate = 16000
        augmenter = Compose([Clip(a_min=-0.1, a_max=0.1, p=1.0)])
        samples = augmenter(samples=samples, sample_rate=sample_rate)

        # I used str here because it doesn't work otherwise
        # TODO: fix this issue
        self.assertEqual(str(np.amin(samples)), '-0.1')
        self.assertEqual(str(np.amax(samples)), '0.1')
        self.assertEqual(samples.dtype, np.float32)
        self.assertEqual(len(samples), 4)

    def test_multichannel(self):
        samples = np.array(
            [[0.9, 0.5, -0.25, -0.125, 0.0], [0.95, 0.5, -0.25, -0.125, 0.0]],
            dtype=np.float32,
        )
        sample_rate = 16000
        augmenter = Compose([Clip(a_min=-0.1, a_max=0.1, p=1.0)])
        samples = augmenter(samples=samples, sample_rate=sample_rate)

        # I used str here because it doesn't work otherwise
        # TODO: fix this issue
        self.assertEqual(str(np.amin(samples)), '-0.1')
        self.assertEqual(str(np.amax(samples)), '0.1')
        self.assertEqual(samples.dtype, np.float32)
