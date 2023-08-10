import random
import warnings
from typing import Optional, Callable

import numpy as np

from audiomentations.core.transforms_interface import BaseWaveformTransform

CROSSFADE_DURATION_EPSILON = 0.00025


class RepeatPart(BaseWaveformTransform):
    """
    Select a part of the audio and repeat that part a number of times
    """

    supports_multichannel = True

    def __init__(
        self,
        min_repeats: int = 1,
        max_repeats: int = 3,
        min_part_duration: float = 0.25,
        max_part_duration: float = 1.2,
        mode: str = "insert",
        crossfade_duration: float = 0.005,
        part_transform: Optional[Callable[[np.ndarray, int], np.ndarray]] = None,
        p: float = 0.5,
    ):
        """
        TODO: docstring goes here

        Note that a part_transform that makes the part shorter is only supported if the
        transformed part is at least two times the crossfade duration.

        Note also that the length of inputs you give it must be compatible with the part
        durations and any crossfade durations. If you give it an input that is too short,
        you'll get a warning and no operation is applied to the signal.

        TODO: Note that setting `crossfade_duration` to 0.0 will disable crossfading.

        :param p: The probability of applying this transform
        """
        super().__init__(p)

        if min_repeats < 1:
            raise ValueError("min_repeats must be >= 1")
        if max_repeats < min_repeats:
            raise ValueError("max_repeats must be >= min_repeats")
        self.min_repeats = min_repeats
        self.max_repeats = max_repeats
        if min_part_duration < 0.0:
            raise ValueError("min_part_duration must be >= 0.0")
        if max_part_duration < min_part_duration:
            raise ValueError("max_part_duration must be >= min_part_duration")
        self.min_part_duration = min_part_duration
        self.max_part_duration = max_part_duration
        if mode not in ("insert", "replace"):
            raise ValueError('mode must be set to either "insert" or "replace"')
        self.mode = mode

        if crossfade_duration == 0.0:
            self.crossfade = False
        if crossfade_duration < 0.0:
            raise ValueError("crossfade_duration must be >= 0.0")
        elif crossfade_duration < CROSSFADE_DURATION_EPSILON:
            raise ValueError(
                "When crossfade_duration is set to a positive number, it must be >="
                f" {CROSSFADE_DURATION_EPSILON}"
            )
        else:
            self.crossfade = True
        if min_part_duration < 2 * crossfade_duration:
            raise ValueError(
                "crossfade_duration must be >= 2 * min_part_duration. You can fix this"
                " error by increasing min_part_duration or by decreasing"
                " crossfade_duration"
            )
        self.crossfade_duration = crossfade_duration
        self.part_transform = part_transform

    def randomize_parameters(self, samples: np.ndarray, sample_rate: int):
        super().randomize_parameters(samples, sample_rate)
        if self.parameters["should_apply"]:
            self.parameters["part_num_samples"] = random.randint(
                int(self.min_part_duration * sample_rate),
                int(self.max_part_duration * sample_rate),
            )
            if self.parameters["part_num_samples"] > samples.shape[-1]:
                # The input sound is not long enough for applying the transform in this case
                self.parameters["should_apply"] = False
                return

            self.parameters["repeats"] = random.randint(
                self.min_repeats, self.max_repeats
            )
            self.parameters["part_start_index"] = random.randint(
                0, samples.shape[-1] - self.parameters["part_num_samples"]
            )

    @staticmethod
    def get_sqrt_fade_in_mask(length):
        return np.sqrt(np.linspace(0, 1, length, dtype=np.float32))

    @staticmethod
    def get_sqrt_fade_out_mask(fade_in_mask: np.ndarray):
        return 1.0 - fade_in_mask

    def apply(self, samples: np.ndarray, sample_rate: int):
        crossfade_length = 0
        half_crossfade_length = 0
        fade_in_mask = None
        fade_out_mask = None
        if self.crossfade:
            crossfade_length = int(self.crossfade_duration * sample_rate)
            if crossfade_length < 2:
                warnings.warn(
                    "crossfade_duration is too small for the given sample rate. Using a"
                    " crossfade length of 2 samples."
                )
                crossfade_length = 2
            elif crossfade_length % 2 == 1:
                crossfade_length += 1
            half_crossfade_length = crossfade_length // 2
            if half_crossfade_length > self.parameters["part_start_index"]:
                raise Exception(
                    "there is a problem! not enough space for crossfade. TODO: Update"
                    " randomize_parameters so it does not select invalid params"
                )  # TODO
            fade_in_mask = self.get_sqrt_fade_in_mask(crossfade_length)
            fade_out_mask = self.get_sqrt_fade_out_mask(fade_in_mask)

        if self.crossfade:
            part = samples[
                ...,
                self.parameters["part_start_index"]
                - half_crossfade_length : self.parameters["part_start_index"]
                + self.parameters["part_num_samples"]
                + half_crossfade_length,
            ]
        else:
            part = samples[
                ...,
                self.parameters["part_start_index"] : self.parameters[
                    "part_start_index"
                ]
                + self.parameters["part_num_samples"],
            ]

        repeats_start_index = (
            self.parameters["part_start_index"] + self.parameters["part_num_samples"]
        )

        last_end_index = repeats_start_index
        parts = []
        for i in range(self.parameters["repeats"]):
            start_idx = last_end_index
            if self.crossfade:
                if i == 0:
                    start_idx -= half_crossfade_length
                else:
                    start_idx -= crossfade_length

            part_array = np.copy(part)

            if self.part_transform:
                part_array = self.part_transform(part_array, sample_rate)
                if self.crossfade and part_array.shape[-1] < 2 * crossfade_length:
                    raise ValueError(
                        "Applying a part_transform that makes a part shorter than 2 *"
                        " crossfade_duration is not supported"
                    )

            last_end_index = start_idx + part_array.shape[-1]

            if self.crossfade:
                part_array[..., :crossfade_length] *= fade_in_mask
                part_array[..., -crossfade_length:] *= fade_out_mask

            stop = False
            if self.mode == "replace" and last_end_index > samples.shape[-1]:
                limited_part_length = samples.shape[-1] - start_idx
                last_end_index = start_idx + limited_part_length
                part_array = part_array[..., :limited_part_length]
                stop = True

            parts.append(
                {"array": part_array, "start_idx": start_idx, "end_idx": last_end_index}
            )
            if stop:
                break

        result_length = samples.shape[-1]
        if self.mode == "insert":
            result_length += (
                parts[-1]["end_idx"] - parts[0]["start_idx"] - crossfade_length
            )

        if samples.ndim == 1:
            result_shape = (result_length,)
        else:
            result_shape = (samples.shape[0], result_length)

        result_placeholder = np.zeros(shape=result_shape, dtype=np.float32)

        if self.crossfade:
            result_placeholder[..., : repeats_start_index - half_crossfade_length] = (
                samples[..., : repeats_start_index - half_crossfade_length]
            )
            result_placeholder[
                ...,
                repeats_start_index
                - half_crossfade_length : repeats_start_index
                + half_crossfade_length,
            ] = (
                fade_out_mask
                * samples[
                    ...,
                    repeats_start_index
                    - half_crossfade_length : repeats_start_index
                    + half_crossfade_length,
                ]
            )
        else:
            result_placeholder[..., :repeats_start_index] = samples[
                ..., :repeats_start_index
            ]

        if self.crossfade:
            # add
            for part in parts:
                result_placeholder[..., part["start_idx"] : part["end_idx"]] += part[
                    "array"
                ]
        else:
            # set
            for part in parts:
                result_placeholder[..., part["start_idx"] : part["end_idx"]] = part[
                    "array"
                ]
        del parts

        if self.mode == "insert":
            if self.crossfade:
                result_placeholder[
                    ..., last_end_index - crossfade_length : last_end_index
                ] += (
                    fade_in_mask
                    * samples[
                        ...,
                        -(result_length - last_end_index)
                        - crossfade_length : -(result_length - last_end_index),
                    ]
                )

            result_placeholder[..., last_end_index:] = samples[
                ..., -(result_length - last_end_index) :
            ]
        else:
            if self.crossfade:
                result_placeholder[
                    ..., last_end_index - crossfade_length : last_end_index
                ] += (
                    fade_in_mask
                    * samples[..., last_end_index - crossfade_length : last_end_index]
                )
            if last_end_index < result_length:
                result_placeholder[..., last_end_index:] = samples[..., last_end_index:]
        return result_placeholder

    def freeze_parameters(self):
        super().freeze_parameters()
        if hasattr(self.part_transform, "freeze_parameters"):
            self.part_transform.freeze_parameters()

    def unfreeze_parameters(self):
        super().unfreeze_parameters()
        if hasattr(self.part_transform, "unfreeze_parameters"):
            self.part_transform.unfreeze_parameters()
